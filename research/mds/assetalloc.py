"""Multi-asset strategic & tactical asset allocation.

**Strategic (SAA):** allocate across asset classes by *risk*, not naive dollars — true **equal-risk-
contribution risk parity** (correlation-aware, and distinct from inverse-vol, which ignores the
correlations), **minimum-variance**, and long-only **max-Sharpe** — benchmarked against a static 60/40.

**Tactical (TAA):** a predictive asset-class overlay that tilts the risk-parity base toward asset
classes with positive trailing (time-series) momentum — a simple "predictive asset-class model".

Everything is **walk-forward and cost-aware** (weights fit on trailing data, earned out-of-sample,
turnover charged on rebalance) and judged by the same overfitting-aware gauntlet as the rest of the
research (`mds/validation.py`). Pure/NumPy — no I/O, unit-tested; `run_assetalloc.py` feeds it real ETF data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sstats
from scipy.optimize import minimize

from . import validation as val

TRADING_DAYS = 252


def _shrink_cov(returns: pd.DataFrame) -> np.ndarray:
    """Annualized covariance with **Ledoit-Wolf shrinkage** — keeps the mean-variance optimizers from
    error-maximizing on a noisy, ill-conditioned sample covariance (a short window over correlated
    assets). Falls back to a fixed-intensity shrink toward the average-variance diagonal if sklearn
    is unavailable."""
    R = np.asarray(returns, dtype=float)
    try:
        from sklearn.covariance import LedoitWolf
        cov = LedoitWolf().fit(R).covariance_
    except Exception:  # noqa: BLE001 — degrade gracefully to a fixed-λ shrink
        s = np.atleast_2d(np.cov(R, rowvar=False))
        avg = float(np.mean(np.diag(s)))
        cov = 0.7 * s + 0.3 * avg * np.eye(s.shape[0])
    return np.asarray(cov) * TRADING_DAYS

# A diversified asset-class proxy universe (liquid ETFs). 60/40 benchmark = SPY / IEF.
UNIVERSE = {
    "SPY": "US equities", "EFA": "Intl equities", "IEF": "US Treasuries",
    "LQD": "IG credit", "GLD": "Gold", "DBC": "Commodities",
}


# ── Allocators: covariance (annualized) → long-only weights summing to 1 ──────────────────────────
def equal_weight(n: int) -> np.ndarray:
    return np.ones(n) / n


def inverse_vol(cov: np.ndarray) -> np.ndarray:
    """1/σ weights — a naive 'risk parity' that ignores correlations (contrast with `risk_parity`)."""
    sd = np.sqrt(np.diag(np.asarray(cov, float)))
    w = np.where(sd > 0, 1.0 / sd, 0.0)
    return w / w.sum()


def risk_parity(cov: np.ndarray, iters: int = 1000, tol: float = 1e-10) -> np.ndarray:
    """**Equal risk contribution**: each asset contributes the same share of portfolio variance. Unlike
    inverse-vol this accounts for the full covariance (cyclical-coordinate algorithm, Chaves et al. 2012)."""
    cov = np.asarray(cov, float)
    n = len(cov)
    w = np.ones(n) / n
    budget = np.ones(n) / n                       # equal risk budgets
    for _ in range(iters):
        w_prev = w.copy()
        var = float(w @ cov @ w)                  # target per-asset risk contribution is budget·σ²
        for i in range(n):
            others = cov[i] @ w - cov[i, i] * w[i]
            a = cov[i, i]
            if a > 0:
                w[i] = (-others + np.sqrt(others * others + 4 * a * budget[i] * var)) / (2 * a)
        w = np.maximum(w, 0.0)
        s = w.sum()
        w = w / s if s > 0 else np.ones(n) / n
        if np.max(np.abs(w - w_prev)) < tol:
            break
    return w


def min_variance(cov: np.ndarray) -> np.ndarray:
    """Long-only minimum-variance portfolio (sum to 1), solved with SLSQP. Falls back to inverse-vol
    if the optimizer fails to converge (rather than trusting a non-converged `res.x`)."""
    cov = np.asarray(cov, float)
    n = len(cov)
    res = minimize(lambda w: w @ cov @ w, np.ones(n) / n, method="SLSQP",
                   bounds=[(0.0, 1.0)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                   options={"maxiter": 500, "ftol": 1e-12})
    return _clean_weights(res.x, n) if res.success else inverse_vol(cov)


def max_sharpe(mu: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Long-only tangency (max-Sharpe) portfolio. Uses the sample mean for `mu` — deliberately included
    so the study can *show* how mean-estimate fragility makes it underperform risk parity out-of-sample."""
    cov = np.asarray(cov, float)
    mu = np.asarray(mu, float)
    n = len(cov)

    def neg_sharpe(w):
        vol = np.sqrt(w @ cov @ w)
        return -(w @ mu) / vol if vol > 0 else 0.0

    res = minimize(neg_sharpe, np.ones(n) / n, method="SLSQP",
                   bounds=[(0.0, 1.0)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
                   options={"maxiter": 500, "ftol": 1e-12})
    return _clean_weights(res.x, n) if res.success else inverse_vol(cov)


def _clean_weights(w: np.ndarray, n: int) -> np.ndarray:
    w = np.maximum(np.asarray(w, float), 0.0)
    s = w.sum()
    return w / s if s > 0 else np.ones(n) / n


def risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Each asset's contribution to portfolio variance (for testing that risk parity equalizes them)."""
    w, cov = np.asarray(w, float), np.asarray(cov, float)
    return w * (cov @ w)


# ── Tactical overlay: a predictive asset-class momentum tilt ──────────────────────────────────────
def ts_momentum(prices: pd.DataFrame, lookback: int = 126) -> np.ndarray:
    """Trailing total return per asset over `lookback` days — the time-series-momentum signal."""
    if len(prices) <= lookback:
        return np.zeros(prices.shape[1])
    return (prices.iloc[-1] / prices.iloc[-lookback - 1] - 1.0).to_numpy()


def momentum_tilt(base_w: np.ndarray, mom: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Long-only tilt of the risk-parity base toward higher-momentum assets (z-scored), renormalized."""
    mom = np.asarray(mom, float)
    sd = mom.std()
    z = (mom - mom.mean()) / sd if sd > 0 else np.zeros_like(mom)
    w = np.asarray(base_w, float) * np.clip(1.0 + strength * z, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else base_w


# ── Walk-forward backtest ─────────────────────────────────────────────────────────────────────────
def _weights_for(method: str, window: pd.DataFrame, prices_to_t: pd.DataFrame, mom_lookback: int) -> np.ndarray:
    # The mean-variance solvers get a Ledoit-Wolf-shrunk covariance (they're the ones that blow up on
    # a raw, ill-conditioned sample cov); risk parity / inverse-vol are robust to the raw estimate.
    if method in ("min_variance", "max_sharpe"):
        cov = _shrink_cov(window)
    else:
        cov = window.cov().to_numpy() * TRADING_DAYS
    n = cov.shape[0]
    if method == "equal":
        return equal_weight(n)
    if method == "inverse_vol":
        return inverse_vol(cov)
    if method == "risk_parity":
        return risk_parity(cov)
    if method == "min_variance":
        return min_variance(cov)
    if method == "max_sharpe":
        return max_sharpe(window.mean().to_numpy() * TRADING_DAYS, cov)
    if method == "risk_parity_taa":
        return momentum_tilt(risk_parity(cov), ts_momentum(prices_to_t, mom_lookback))
    raise ValueError(f"unknown method: {method}")


def backtest(prices: pd.DataFrame, method: str = "risk_parity", lookback: int = 252,
             rebalance: int = 21, cost_bps: float = 10.0, mom_lookback: int = 126) -> dict:
    """Walk-forward: every `rebalance` days, fit weights on the trailing `lookback` window and hold them
    out-of-sample; charge `cost_bps` on turnover. Returns the net daily series + honest stats."""
    rets = prices.pct_change().dropna()
    dates = rets.index
    n = rets.shape[1]
    w_drift = np.zeros(n)                             # holdings carried in from the previous block (drifted)
    net = pd.Series(0.0, index=dates)
    for t in range(lookback, len(rets), rebalance):
        window = rets.iloc[t - lookback:t]
        w = _weights_for(method, window, prices.iloc[: t + 1], mom_lookback)
        block = rets.iloc[t:t + rebalance].to_numpy()
        port = block @ w
        turn = float(np.abs(w - w_drift).sum())      # trade = new target vs. what we actually still hold
        if len(port):
            port[0] -= turn * cost_bps / 1e4         # charge turnover cost on the rebalance day
            net.iloc[t:t + len(port)] = port
        w_drift = _drift(w, block)                    # let the new weights drift with returns over the block
    net = net.iloc[lookback:]
    return {"method": method, **_stats(net), "net": net}


def _drift(w: np.ndarray, block: np.ndarray) -> np.ndarray:
    """Weights after holding through a block of returns — so the NEXT rebalance's turnover is measured
    against what's actually held, not the stale target (a static book still pays drift-correction cost)."""
    grown = w * np.prod(1.0 + block, axis=0)
    s = grown.sum()
    return grown / s if s > 0 else w


def sixty_forty(prices: pd.DataFrame, eq: str = "SPY", bond: str = "IEF",
                lookback: int = 252, rebalance: int = 21, cost_bps: float = 10.0) -> dict:
    """Static 60/40 (equities/bonds), rebalanced on the same schedule — the benchmark to beat."""
    sub = prices[[eq, bond]]
    target = np.array([0.60, 0.40])
    rets = sub.pct_change().dropna()
    net = pd.Series(0.0, index=rets.index)
    w_drift = np.zeros(2)
    for t in range(lookback, len(rets), rebalance):
        block = rets.iloc[t:t + rebalance].to_numpy()
        port = block @ target
        if len(port):
            # rebalancing back to 60/40 trades against the drifted holdings — a real, non-zero cost
            port[0] -= float(np.abs(target - w_drift).sum()) * cost_bps / 1e4
            net.iloc[t:t + len(port)] = port
        w_drift = _drift(target, block)
    net = net.iloc[lookback:]
    return {"method": "60/40", **_stats(net), "net": net}


def _stats(net: pd.Series, ppy: int = TRADING_DAYS) -> dict:
    r = net.to_numpy()
    r = r[np.isfinite(r)]
    if len(r) < 8 or r.std() == 0:
        return {"ann_return": 0.0, "ann_vol": 0.0, "sharpe": 0.0, "hac_t": 0.0,
                "boot_lo": 0.0, "boot_hi": 0.0, "max_drawdown": 0.0, "n_days": len(r)}
    prod = float(np.prod(1 + r))
    ann_ret = float(prod ** (ppy / len(r)) - 1) if prod > 0 else -1.0   # undefined if the book is wiped out
    ann_vol = float(r.std() * np.sqrt(ppy))
    sharpe = float(r.mean() / r.std() * np.sqrt(ppy))
    hac_t = float(val.newey_west_sharpe_tstat(r))
    lo, hi = val.block_bootstrap_sharpe_ci(r, ppy=ppy)
    equity = np.cumprod(1 + r)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.where(peak > 0, equity / peak - 1.0, 0.0).min())
    return {"ann_return": round(ann_ret, 4), "ann_vol": round(ann_vol, 4), "sharpe": round(sharpe, 3),
            "hac_t": round(hac_t, 2), "boot_lo": round(float(lo), 2), "boot_hi": round(float(hi), 2),
            "max_drawdown": round(max_dd, 4), "n_days": len(r)}


def study(prices: pd.DataFrame, cost_bps: float = 10.0, lookback: int = 252, rebalance: int = 21) -> dict:
    """Run every allocator + the 60/40 benchmark, then apply the same selection-aware gauntlet as the
    rest of the research — because backtesting 7 strategies on one sample IS multiple testing."""
    methods = ["equal", "inverse_vol", "risk_parity", "min_variance", "max_sharpe", "risk_parity_taa"]
    rows = [backtest(prices, m, lookback, rebalance, cost_bps) for m in methods]
    rows.append(sixty_forty(prices, lookback=lookback, rebalance=rebalance, cost_bps=cost_bps))
    nets = {r["method"]: r["net"] for r in rows}
    gauntlet = _gauntlet(nets)
    for r in rows:
        r.pop("net", None)
    return {"assets": list(prices.columns), "cost_bps": cost_bps, "results": rows, "gauntlet": gauntlet}


def _gauntlet(nets: dict) -> dict:
    """Selection-aware honesty on the strategy SET: PBO across all of them, the Deflated Sharpe of the
    best (deflated for having tried this many), the multiple-testing t-bar, and the min-detectable
    Sharpe — is the sample even powered to distinguish these from luck?"""
    mat = pd.DataFrame(nets).dropna()               # T × M aligned net-return matrix
    n, m = mat.shape
    pp = mat.mean() / mat.std(ddof=0)               # per-period Sharpe of each strategy
    best = str(pp.idxmax())
    r_best = mat[best].to_numpy()
    dsr = float(val.deflated_sharpe(float(pp[best]), n, float(sstats.skew(r_best)),
                                    float(sstats.kurtosis(r_best, fisher=False)),  # non-excess kurtosis
                                    m, float(np.var(pp.to_numpy(), ddof=1))))
    return {
        "best": best,
        "best_sharpe_ann": round(float(pp[best]) * np.sqrt(TRADING_DAYS), 3),
        "best_hac_t": round(float(val.newey_west_sharpe_tstat(r_best)), 2),
        "bonferroni_t": round(float(val.bonferroni_z(m)), 2),
        "deflated_sharpe": round(dsr, 3),
        "pbo": round(float(val.pbo(mat.to_numpy())["pbo"]), 3),
        "min_detectable_sharpe": round(float(val.min_detectable_sharpe(n, ppy=TRADING_DAYS)), 2),
        "n_strategies": m, "n_days": n,
    }
