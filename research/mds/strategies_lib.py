"""A library of strategies expressed against the `engine.Strategy` interface — proof the SDK unifies the
formerly-scattered studies. Each adapter *reuses* the existing research modules (allocation math in
`assetalloc`, trend signals in `trend`) rather than reimplementing them; the engine supplies one common
walk-forward loop, evaluation, gauntlet, and tearsheet for all of them.

Add a new strategy by subclassing `engine.Strategy` — it inherits the entire pipeline for free.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import assetalloc as aa
from . import trend as tr
from .engine import Strategy

TRADING_DAYS = 252


class EqualWeight(Strategy):
    """1/N — the DeMiguel benchmark that's surprisingly hard to beat out-of-sample."""
    name = "equal-weight"
    warmup = 60

    def __init__(self, symbols: list[str]):
        self._symbols = list(symbols)

    def symbols(self) -> list[str]:
        return self._symbols

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        n = len(self._symbols)
        return np.ones(n) / n


class SixtyForty(Strategy):
    """Static 60/40 equity/bond — the classic benchmark to beat."""
    name = "60/40"
    warmup = 60

    def __init__(self, equity: str = "SPY", bond: str = "IEF"):
        self.equity, self.bond = equity, bond

    def symbols(self) -> list[str]:
        return [self.equity, self.bond]

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        return np.array([0.60, 0.40])


class RiskParity(Strategy):
    """Equal-risk-contribution risk parity on a trailing covariance (reuses `assetalloc.risk_parity`)."""
    name = "risk-parity"

    def __init__(self, symbols: list[str], lookback: int = 252):
        self._symbols, self.lookback = list(symbols), lookback
        self.warmup = lookback + 2

    def symbols(self) -> list[str]:
        return self._symbols

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        win = prices.iloc[t - self.lookback:t].pct_change().dropna()
        cov = aa._shrink_cov(win)                     # Ledoit-Wolf shrunk, annualized
        return aa.risk_parity(cov)


class MinVariance(Strategy):
    """Long-only minimum-variance (reuses `assetalloc.min_variance`, with its inverse-vol fallback)."""
    name = "min-variance"

    def __init__(self, symbols: list[str], lookback: int = 252):
        self._symbols, self.lookback = list(symbols), lookback
        self.warmup = lookback + 2

    def symbols(self) -> list[str]:
        return self._symbols

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        win = prices.iloc[t - self.lookback:t].pct_change().dropna()
        return aa.min_variance(aa._shrink_cov(win))


class TimeSeriesMomentum(Strategy):
    """Diversified long/short trend book: multi-timescale risk-adjusted signal (reuses `trend.trend_score`)
    × inverse-vol legs, scaled to a constant portfolio vol on the trailing covariance. The trend study's
    core, expressed in ~15 lines against the SDK."""
    name = "ts-momentum"
    warmup = 260

    def __init__(self, symbols: list[str], target_vol: float = 0.10, cov_lookback: int = 252):
        self._symbols, self.target_vol, self.cov_lookback = list(symbols), target_vol, cov_lookback

    def symbols(self) -> list[str]:
        return self._symbols

    def prepare(self, prices: pd.DataFrame) -> None:
        self._sig = tr.trend_score(prices)                        # causal multi-timescale signal panel
        self._inv_vol = tr._inv_vol(prices.pct_change())          # causal per-asset 1/σ

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        s = np.nan_to_num(self._sig.iloc[t - 1].to_numpy(dtype=float))         # prior-close signal
        w = s * np.nan_to_num(self._inv_vol.iloc[t - 1].to_numpy(dtype=float))  # inverse-vol legs
        g = np.abs(w).sum()
        if g > 0:
            w = w / g
        cov = prices.iloc[t - self.cov_lookback:t].pct_change().dropna().cov().to_numpy() * TRADING_DAYS
        pv = float(np.sqrt(max(w @ cov @ w, 0.0)))                # scale to constant portfolio vol
        return w * (self.target_vol / pv) if pv > 0 else w
