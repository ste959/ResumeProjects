"""Model zoo + the cost-aware acid test for microstructure signals.

Trains a range of models (linear → gradient boosting → a small neural net) to predict the
forward mid return from order-book features, using **walk-forward out-of-sample** validation,
then subjects each to the test that actually matters: a backtest that pays the spread to trade.

A high information coefficient that evaporates after costs is the honest — and common — result
on noisy financial data. Reporting the gross-vs-net gap *is* the finding.
"""

from __future__ import annotations

import numpy as np

from . import lob


def _model_factories():
    """Lazily import sklearn so the rest of the package works without it installed."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.neural_network import MLPRegressor

    return {
        "ridge": lambda: Ridge(alpha=1.0),
        "gbm": lambda: HistGradientBoostingRegressor(
            max_depth=4, max_iter=150, learning_rate=0.05, l2_regularization=1.0),
        "mlp": lambda: MLPRegressor(
            hidden_layer_sizes=(32, 16), alpha=1e-3, max_iter=200,
            early_stopping=True, random_state=0),
    }


def walk_forward_predict(df, features, factory, folds: int = 5) -> np.ndarray:
    """Out-of-sample predictions via expanding-window walk-forward. The scaler is fit on the
    training fold ONLY (fitting it on all data would leak test-set statistics into training)."""
    from sklearn.preprocessing import StandardScaler

    X = df[features].to_numpy(dtype=float)
    y = df["fwd_ret"].to_numpy(dtype=float)
    pred = np.full(len(df), np.nan)
    for train, test in lob.walk_forward_splits(len(df), folds=folds):
        scaler = StandardScaler().fit(X[train])
        model = factory()
        model.fit(scaler.transform(X[train]), y[train])
        pred[test] = model.predict(scaler.transform(X[test]))
    return pred


def _sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    s = x.std(ddof=0)
    # Per-sample Sharpe scaled by √N — a comparison proxy (samples are event-, not clock-, spaced).
    return float(x.mean() / s * np.sqrt(len(x))) if s > 0 and len(x) else 0.0


def net_backtest(fwd_ret, position, spread_bps, fee_bps: float = 1.0, horizon: int = 1) -> dict:
    """Backtest a directional position against realised forward returns, charging the
    **half-spread + fees on every trade** — the cost of crossing to enter/exit a microstructure
    signal. One-period lag (position at t earns the return realised after t).

    The label is a horizon-H forward return, so consecutive samples OVERLAP by H−1 steps. Trading
    every step would book each price move ~H times and treat autocorrelated samples as IID
    (inflating the Sharpe by ~√H). We therefore account on NON-OVERLAPPING samples — take every
    H-th observation — so each realised return is counted once and the samples don't overlap. At
    H=1 this is a no-op."""
    fwd_ret = np.asarray(fwd_ret, dtype=float)
    position = np.nan_to_num(np.asarray(position, dtype=float))
    spread_bps = np.asarray(spread_bps, dtype=float)

    if horizon > 1:
        fwd_ret = fwd_ret[::horizon]
        position = position[::horizon]
        spread_bps = spread_bps[::horizon]

    held = np.roll(position, 1)
    held[0] = 0.0
    gross = held * fwd_ret

    turnover = np.abs(np.diff(np.concatenate([[0.0], position])))
    cost = turnover * ((spread_bps / 2.0 + fee_bps) / 1e4)
    net = gross - cost

    return {
        "gross_sharpe": _sharpe(gross),
        "net_sharpe": _sharpe(net),
        "gross_ret_bps": float(gross.sum() * 1e4),
        "net_ret_bps": float(net.sum() * 1e4),
        "cost_bps": float(cost.sum() * 1e4),
        "avg_turnover": float(turnover.mean()) if turnover.size else 0.0,
    }


def evaluate(df, features=None, folds: int = 5, fee_bps: float = 1.0, horizon: int = 1) -> dict:
    """Run the whole zoo: for each model, out-of-sample IC (with an overlap-aware significance
    error bar) and the cost-aware, non-overlapping backtest. `horizon` must match the label
    horizon used to build `df` so the significance and P&L don't double-count overlapping samples."""
    features = features or lob.FEATURES
    fwd = df["fwd_ret"].to_numpy(dtype=float)
    spread = df["spread_bps"].to_numpy(dtype=float)

    results = {}
    for name, factory in _model_factories().items():
        pred = walk_forward_predict(df, features, factory, folds=folds)
        mask = np.isfinite(pred) & np.isfinite(fwd)
        ic = lob.information_coefficient(pred[mask], fwd[mask])
        # Effective sample size discounts the horizon overlap so the IC error bar isn't overstated.
        n_eff = int(mask.sum()) // max(horizon, 1)
        sig = lob.ic_significance(ic["spearman"], n_eff)
        position = np.sign(pred)  # long/short by predicted direction of the next move
        bt = net_backtest(fwd[mask], position[mask], spread[mask], fee_bps=fee_bps, horizon=horizon)
        results[name] = {"ic_pearson": ic["pearson"], "ic_spearman": ic["spearman"],
                         "ic_t": sig["t_stat"], "ic_ci_low": sig["ci_low"],
                         "ic_ci_high": sig["ci_high"], "oos_n": int(mask.sum()),
                         "n_eff": sig["n_eff"], **bt}
    return results
