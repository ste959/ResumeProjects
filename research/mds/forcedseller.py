"""The Forced Seller — anticipating mechanical volatility-target deleveraging.

A large, growing pool of AUM (volatility-control funds inside variable annuities, risk-parity, some CTAs)
targets a **constant portfolio volatility**. Its equity exposure is mechanically `target_vol / realized_vol`,
so when realized vol **rises it must sell** equities to keep vol at target, and when vol **falls it must
re-lever**. This flow is price-insensitive, huge (hundreds of $B), spread over several days (they scale, not
snap), and — crucially — **estimable from public price data alone**. Unlike the leveraged-ETF flow (a
one-day burst that *reverts*), this flow is *sustained* over days, so you **ride** it, not fade it: front-run
the coming forced selling/buying.

The estimator is the change in the reaction function: `Δ(target_vol / realized_vol)`. Negative = the machines
are deleveraging (sell pressure ahead); positive = re-levering (buy pressure ahead). The honest question this
study answers: does anticipating the *flow* add anything beyond simply vol-targeting your own book
(Moreira–Muir)? Pure NumPy/pandas; strategies plug into the engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import stats as st
from .engine import Strategy

TRADING_DAYS = 252


def realized_vol(rets: pd.Series, window: int = 20) -> pd.Series:
    """Annualized trailing realized volatility."""
    return rets.rolling(window).std() * np.sqrt(TRADING_DAYS)


def target_exposure(rvol: pd.Series, target_vol: float = 0.15, max_lev: float = 2.0) -> pd.Series:
    """The vol-control reaction function: exposure = target_vol / realized_vol, capped. This is what the
    machines hold; its changes are what they're forced to trade."""
    return (target_vol / rvol.replace(0, np.nan)).clip(lower=0.0, upper=max_lev)


def forced_flow(exposure: pd.Series, lookback: int = 5) -> pd.Series:
    """Δexposure over `lookback` days — the recent forced rebalance. < 0 = deleveraging (sell pressure
    coming); > 0 = re-levering (buy pressure). This is the signal you front-run."""
    return exposure.diff(lookback)


def flow_signal(rets: pd.Series, target_vol: float = 0.15, max_lev: float = 2.0,
                vol_window: int = 20, lookback: int = 5, scale: float = 0.5) -> pd.Series:
    """Directional position in [−1, 1] from the estimated forced flow: long when the machines are forced to
    buy, short when forced to sell (ride the sustained flow), saturated with tanh."""
    e = target_exposure(realized_vol(rets, vol_window), target_vol, max_lev)
    return np.tanh(forced_flow(e, lookback) / scale)


def forward_predictability(rets: pd.Series, signal: pd.Series, horizons=(1, 3, 5, 10)) -> pd.DataFrame:
    """Does the forced-flow estimate predict forward returns *in its own direction* (deleveraging → down)?
    Regress the forward h-day return on the signal at each horizon; a positive, significant coefficient is
    the mechanism."""
    rows = []
    for h in horizons:
        fwd = rets.shift(-1).rolling(h).sum().shift(-(h - 1))         # return over the next h days
        df = pd.DataFrame({"x": signal, "y": fwd}).dropna()
        if len(df) < 60:
            continue
        fit = st.ols(np.column_stack([np.ones(len(df)), df["x"].to_numpy()]), df["y"].to_numpy())
        rows.append({"horizon": h, "coef": round(float(fit["beta"][1]), 4),
                     "t_stat": round(float(fit["tstat"][1]), 2), "n": len(df)})
    return pd.DataFrame(rows)


# ── Strategies (plug into engine.run) ─────────────────────────────────────────────────────────────
class _SingleName(Strategy):
    warmup = 40

    def __init__(self, symbol: str = "SPY"):
        self._symbol = symbol

    def symbols(self):
        return [self._symbol]


class ForcedSeller(_SingleName):
    """Ride the anticipated vol-control flow: position = tanh(Δexposure / scale)."""
    name = "forced-seller"

    def __init__(self, symbol: str = "SPY", target_vol: float = 0.15, max_lev: float = 2.0,
                 vol_window: int = 20, lookback: int = 5, scale: float = 0.5):
        super().__init__(symbol)
        self.kw = dict(target_vol=target_vol, max_lev=max_lev, vol_window=vol_window,
                       lookback=lookback, scale=scale)

    def prepare(self, prices):
        self._pos = flow_signal(prices[self._symbol].pct_change(), **self.kw)

    def target_weights(self, prices, t):
        return np.array([np.nan_to_num(self._pos.iloc[t - 1])])


class VolTargetHold(_SingleName):
    """Benchmark: long-only vol-targeting your OWN book (Moreira–Muir) — position = target/realized vol.
    The forced-seller must beat THIS to prove it's the flow, not just generic vol-timing."""
    name = "vol-target-hold"

    def __init__(self, symbol: str = "SPY", target_vol: float = 0.15, max_lev: float = 2.0, vol_window: int = 20):
        super().__init__(symbol)
        self.kw = dict(target_vol=target_vol, max_lev=max_lev, vol_window=vol_window)

    def prepare(self, prices):
        r = prices[self._symbol].pct_change()
        self._pos = target_exposure(realized_vol(r, self.kw["vol_window"]), self.kw["target_vol"],
                                    self.kw["max_lev"])

    def target_weights(self, prices, t):
        return np.array([np.nan_to_num(self._pos.iloc[t - 1])])


class BuyHold(_SingleName):
    name = "buy-hold"

    def target_weights(self, prices, t):
        return np.array([1.0])
