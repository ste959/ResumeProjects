"""Portfolio construction over signals — the systematic trader's core job.

Given several strategies' return streams, decide how to allocate capital/risk across them to
maximize the portfolio's net-of-cost, risk-adjusted return. Everything here is **walk-forward
and out-of-sample**: weights are estimated on a trailing window and applied to the *next* block,
so the reported result is honest and reflects the classic lesson — naive mean-variance
over-fits the estimated means, while risk-parity and covariance shrinkage generalize.

    combined, log = walk_forward_allocate(signal_net_returns, method="risk_parity")
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _shrink_cov(returns: np.ndarray, lam: float = 0.3) -> np.ndarray:
    """Shrink the sample covariance toward a scaled identity with a FIXED intensity λ — this is
    what keeps mean-variance from exploding on a noisy, short estimation window. Note: this is a
    fixed-λ shrink, NOT the analytic Ledoit-Wolf optimum (which derives λ from the data); we keep
    it fixed for transparency and reproducibility, accepting it is not the MSE-optimal intensity."""
    cov = np.atleast_2d(np.cov(returns, rowvar=False))
    avg_var = float(np.mean(np.diag(cov)))
    return (1.0 - lam) * cov + lam * avg_var * np.eye(cov.shape[0])


def optimize_weights(window: pd.DataFrame, method: str = "risk_parity", lam: float = 0.3) -> np.ndarray:
    """Non-negative signal weights that sum to 1, estimated from a trailing return window."""
    R = window.to_numpy(dtype=float)
    n = R.shape[1]
    if method == "equal":
        w = np.ones(n)
    elif method == "inverse_vol":
        vol = R.std(axis=0, ddof=0)
        w = np.divide(1.0, vol, out=np.zeros_like(vol), where=vol > 0)
    elif method == "risk_parity":
        # TRUE equal-risk-contribution (correlation-aware) — not the inverse-vol shortcut. Runs the
        # shared ERC solver on the shrunk covariance so correlated signals are downweighted.
        from .assetalloc import risk_parity as _erc
        return _erc(_shrink_cov(R, lam))
    elif method == "max_sharpe":
        mu = R.mean(axis=0)
        w = np.linalg.solve(_shrink_cov(R, lam), mu)
        w = np.clip(w, 0.0, None)  # long-only: don't short your own signal
    else:
        raise ValueError(f"unknown method: {method}")
    total = w.sum()
    return w / total if total > 0 else np.ones(n) / n


def walk_forward_allocate(signal_returns: pd.DataFrame, method: str = "risk_parity",
                          lookback: int = 126, rebalance: int = 21):
    """Estimate weights on the trailing `lookback` days, hold them for the next `rebalance` days,
    and roll forward. Returns the combined out-of-sample return series and the weight history."""
    R = signal_returns.dropna()
    combined = pd.Series(np.nan, index=R.index)
    log = []
    for start in range(lookback, len(R), rebalance):
        w = optimize_weights(R.iloc[start - lookback:start], method)
        test = R.iloc[start:start + rebalance]
        combined.loc[test.index] = test.to_numpy() @ w
        log.append((R.index[start], w))
    return combined.dropna(), log


def vol_target(returns: pd.Series, target_annual_vol: float = 0.10,
               min_periods: int = 20, max_leverage: float = 3.0) -> pd.Series:
    """Scale a return series to a target annualized volatility, CAUSALLY.

    The sizing at time t may only use information through t-1, otherwise it is look-ahead: a
    full-sample std peeks at the whole path. We estimate volatility with a trailing EXPANDING
    std shifted by one period, so the scale applied to return t is built from returns up to t-1.
    Days before `min_periods` of history (no reliable estimate yet) are left NaN rather than
    sized on a guess. The scale is **capped at `max_leverage`** so a quiet early regime (tiny
    trailing vol) can't imply a runaway leveraged position."""
    trailing_ann = returns.expanding(min_periods=min_periods).std(ddof=0).shift(1) * np.sqrt(TRADING_DAYS)
    scale = (target_annual_vol / trailing_ann.where(trailing_ann > 0)).clip(upper=max_leverage)
    return returns * scale


def vol_managed(returns: pd.Series, target_annual_vol: float = 0.10, window: int = 21,
                min_periods: int = 10, max_leverage: float = 3.0) -> pd.Series:
    """Moreira–Muir (2017) vol-managed overlay: scale each period's exposure inversely to the
    strategy's OWN recent realized variance, targeting `target_annual_vol`, with a leverage cap.

    Unlike `vol_target` (which uses an expanding std, mainly to normalize the level), this uses a
    short ROLLING window — it is a *timing* overlay. The claim (and the reason it's one of the few
    factor-timing results that survives out-of-sample) is that variance is persistent and only
    weakly related to next-period return, so cutting exposure when vol is high raises the Sharpe;
    for momentum specifically it dodges the crash/rebound (Barroso–Santa-Clara). Causal: the scale
    at t uses a trailing window shifted by one, and leverage is capped so a quiet stretch can't
    blow up the book."""
    trailing_ann = returns.rolling(window, min_periods=min_periods).std(ddof=0).shift(1) * np.sqrt(TRADING_DAYS)
    scale = (target_annual_vol / trailing_ann.where(trailing_ann > 0)).clip(upper=max_leverage)
    return returns * scale


def kelly_fraction(returns: pd.Series) -> float:
    """Full-Kelly leverage f* = mean / variance (per period). Practitioners use a FRACTION of
    this — full Kelly is famously too aggressive (its drawdowns are brutal)."""
    var = float(returns.var(ddof=0))
    return float(returns.mean() / var) if var > 0 else 0.0


def sharpe(returns: pd.Series, ppy: int = TRADING_DAYS) -> float:
    r = returns.dropna()
    s = r.std(ddof=0)
    return float(r.mean() / s * np.sqrt(ppy)) if s > 0 and len(r) else 0.0


def metrics(returns: pd.Series) -> dict:
    r = returns.dropna()
    equity = (1.0 + r).cumprod()
    max_dd = float((equity / equity.cummax() - 1.0).min()) if len(equity) else 0.0
    ann = float(equity.iloc[-1] ** (TRADING_DAYS / max(len(r), 1)) - 1.0) if len(r) else 0.0
    return {"sharpe": sharpe(r), "ann_return": ann, "max_drawdown": max_dd,
            "kelly": kelly_fraction(r), "days": int(len(r))}
