"""Portfolio risk math — volatility-targeted sizing and correlation-aware portfolio volatility.

Two ideas a trader would insist on, both pure/numpy so they're unit-tested without any I/O:

  • **Vol-targeting**: size each sleeve to a fixed *risk* budget, not a fixed dollar. A $1,500 position
    in a 90%-vol alt is far riskier than $1,500 in a 60%-vol name; `vol_target_notional` scales the
    notional inversely to the asset's volatility so every sleeve contributes ~the same risk.

  • **Portfolio netting**: the account's real risk is `sqrt(wᵀ Σ w)`, not the naive gross `Σ|w|`. Two
    correlated longs are almost one bet (their risks add), while a long/short pair nets down. The cap
    that matters is on this correlation-aware portfolio vol, not on gross exposure.
"""

from __future__ import annotations

import numpy as np


def returns_from_closes(closes) -> list[float]:
    c = np.asarray(list(closes), dtype=float)
    if len(c) < 2:
        return []
    prev = c[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(prev != 0, np.diff(c) / prev, 0.0)
    return list(r)


def ann_vol(returns, ppy: float) -> float:
    """Annualized volatility of a return series (0 if too short)."""
    r = np.asarray(list(returns), dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return 0.0
    return float(r.std(ddof=0) * np.sqrt(ppy))


def cov_annualized(returns_by_symbol: dict, symbols: list, ppy: float) -> np.ndarray:
    """Annualized return covariance matrix over `symbols`, aligned to the shortest available series."""
    k = len(symbols)
    if k == 0:
        return np.zeros((0, 0))
    series = [np.asarray(returns_by_symbol.get(s, []), dtype=float) for s in symbols]
    n = min((len(x) for x in series), default=0)
    if n < 2:
        return np.zeros((k, k))
    m = np.vstack([x[-n:] for x in series])          # (k, n)
    return np.atleast_2d(np.cov(m, ddof=0)) * ppy


def vol_target_notional(target_vol_usd: float, asset_ann_vol: float, lo: float, hi: float) -> float:
    """Position notional so `notional × asset_vol ≈ target_vol_usd`, clamped to [lo, hi]. Higher-vol
    assets get less notional. Falls back to `lo` when vol is unknown/degenerate."""
    if asset_ann_vol <= 0 or not np.isfinite(asset_ann_vol):
        return lo
    return float(min(hi, max(lo, target_vol_usd / asset_ann_vol)))


def portfolio_vol(weights_usd: dict, symbols: list, cov) -> float:
    """Correlation-aware annualized portfolio volatility in dollars: sqrt(wᵀ Σ w), with w the signed
    position values ($). Captures that correlated longs barely diversify and offsetting legs net down."""
    if len(symbols) == 0:
        return 0.0
    w = np.array([float(weights_usd.get(s, 0.0)) for s in symbols], dtype=float)
    cov = np.asarray(cov, dtype=float)
    if cov.shape != (len(symbols), len(symbols)):
        return 0.0
    return float(np.sqrt(max(0.0, w @ cov @ w)))
