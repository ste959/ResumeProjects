"""Execution & cost realism — the difference between a backtest Sharpe and *alpha under real conditions*.

A flat "10 bps" cost hides the two things that actually decide whether an edge survives contact with the
market: **the spread you cross** and **the impact you cause**, both of which scale with **how much money
you run** relative to how much the asset trades. This module models that:

- **Bid–ask spread** — you pay the half-spread on every trade. Estimated from daily high/low with the
  **Corwin–Schultz (2012)** estimator (hand-rolled, no external library), or an assumed floor.
- **Market impact** — the **square-root law** (Almgren et al.): impact ≈ coef · σ · √(traded / ADV). Big
  trades in thin names move the price against you.
- **Participation cap & partial fills** — you can't trade more than a set fraction of a day's volume; a
  rebalance that wants more only *partially* fills, and the shortfall carries to the next rebalance. This
  is what makes the backtest **capacity-aware**: the same signal costs more at $1B than at $10M.
- **Short borrow & financing** — short legs pay a borrow fee and leverage pays financing, charged daily —
  the carry a long/short or levered book actually bears.

`FlatBps` reproduces the old flat-cost behavior (for comparison and backward-compatibility); the engine
defaults to it, so nothing changes until you opt into `RealisticExecution`. Pure NumPy/pandas — no I/O.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ── Liquidity estimation ──────────────────────────────────────────────────────────────────────────
def corwin_schultz_spread(high: pd.DataFrame, low: pd.DataFrame, window: int = 21) -> pd.DataFrame:
    """Proportional bid–ask spread estimated from 2-day high/low ranges (Corwin & Schultz 2012). The
    insight: the high/low over one day reflects volatility, over two days it also reflects the spread —
    solving the two apart gives a spread estimate from daily bars alone. Negative estimates (noise) are
    floored at 0 and the series is smoothed. Causal (only trailing bars)."""
    hl = (np.log(high / low)) ** 2                              # (ln H/L)² per day
    beta = hl + hl.shift(1)                                     # β_t: this day + the previous day
    hi2 = np.maximum(high, high.shift(1))
    lo2 = np.minimum(low, low.shift(1))
    gamma = (np.log(hi2 / lo2)) ** 2
    den = 3.0 - 2.0 * np.sqrt(2.0)
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / den - np.sqrt(gamma / den)
    s = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))     # proportional spread
    return s.clip(lower=0.0).rolling(window).mean()


def adv_spread(adv_usd: pd.DataFrame, coef: float = 0.0087,
               floor: float = 5e-5, cap: float = 2.5e-3) -> pd.DataFrame:
    """Proportional spread as a decreasing function of dollar ADV — a liquidity-tier proxy calibrated so a
    ~$30B-ADV ETF is sub-basis-point and a ~$200M-ADV name is ~6 bps, clipped to [0.5bp, 25bp]. Realistic
    for ETFs, where Corwin–Schultz overestimates (it reads intraday volatility as spread). This is the
    default; CS is available via `estimate_liquidity(..., method="corwin_schultz")` as a cross-check."""
    s = coef / np.sqrt((adv_usd / 1e6).clip(lower=1e-6))
    return s.clip(lower=floor, upper=cap)


@dataclass
class Liquidity:
    """Per-asset, per-date liquidity inputs the cost model needs (all causal)."""
    adv_usd: pd.DataFrame       # average daily dollar volume (rolling)
    daily_vol: pd.DataFrame     # daily return volatility (rolling)
    spread_frac: pd.DataFrame   # proportional bid-ask spread


def estimate_liquidity(close: pd.DataFrame, volume: pd.DataFrame,
                       high: pd.DataFrame | None = None, low: pd.DataFrame | None = None,
                       adv_window: int = 21, vol_window: int = 63,
                       method: str = "adv") -> Liquidity:
    """Build the `Liquidity` inputs from OHLCV panels. Spread defaults to the ADV-based liquidity-tier
    model (`method="adv"`, realistic for ETFs); `method="corwin_schultz"` uses the high/low estimator
    instead (honest but biased high for liquid names — see `adv_spread`). Both are clipped to [0.5bp, 25bp]."""
    adv = (close * volume).rolling(adv_window).mean()
    vol = close.pct_change().rolling(vol_window).std()
    if method == "corwin_schultz" and high is not None and low is not None:
        spread = corwin_schultz_spread(high, low).reindex_like(close)
        spread = spread.fillna(5e-4).clip(lower=5e-5, upper=2.5e-3)
    else:
        spread = adv_spread(adv).fillna(2.5e-3)
    return Liquidity(adv_usd=adv, daily_vol=vol, spread_frac=spread)


# ── Execution models ──────────────────────────────────────────────────────────────────────────────
class ExecutionModel(ABC):
    """Given a desired rebalance, return the weights actually ACHIEVED and the one-off trading cost (as a
    return). `carry()` returns the daily holding drag (borrow/financing)."""

    @abstractmethod
    def rebalance(self, w_prev: np.ndarray, w_target: np.ndarray, aum: float,
                  liq: dict | None) -> tuple[np.ndarray, float]:
        ...

    def carry(self, w_held: np.ndarray, days: int = 1) -> float:
        return 0.0


class FlatBps(ExecutionModel):
    """The classic flat cost: `bps` on one-way turnover, fills exactly at target, no borrow/financing.
    Kept for backward-compatibility and as the naive baseline to compare realism against."""

    def __init__(self, bps: float = 10.0):
        self.bps = bps

    def rebalance(self, w_prev, w_target, aum, liq):
        w_target = np.asarray(w_target, float)
        turn = float(np.abs(w_target - np.asarray(w_prev, float)).sum())
        return w_target, turn * self.bps / 1e4


@dataclass
class RealisticExecution(ExecutionModel):
    """Spread + square-root market impact + a participation cap (partial fills) + short-borrow/financing.

    impact_coef · σ · √(participation) is the temporary impact per unit traded; `max_participation` is the
    fraction of ADV tradable per rebalance (the rest carries to next time — capacity made explicit)."""
    impact_coef: float = 0.3
    max_participation: float = 0.10
    borrow_bps: float = 50.0        # annual borrow on short notional
    financing_bps: float = 100.0    # annual financing on leverage above 1x gross

    def rebalance(self, w_prev, w_target, aum, liq):
        w_prev, w_target = np.asarray(w_prev, float), np.asarray(w_target, float)
        if liq is None:
            raise ValueError("RealisticExecution needs liquidity (pass `liquidity=` to engine.run)")
        adv = np.asarray(liq["adv"], float)
        vol = np.nan_to_num(np.asarray(liq["vol"], float))
        spread = np.nan_to_num(np.asarray(liq["spread"], float))

        desired_notional = (w_target - w_prev) * aum
        cap = self.max_participation * np.where(adv > 0, adv, np.inf)     # $ tradable this rebalance
        filled = np.clip(desired_notional, -cap, cap)                     # participation-capped → partial fill
        w_achieved = w_prev + filled / aum

        traded = np.abs(filled)
        participation = np.where(adv > 0, traded / adv, 0.0)
        impact = self.impact_coef * vol * np.sqrt(participation)          # square-root impact (fraction)
        cost_usd = (spread / 2.0 + impact) * traded                       # half-spread + impact, on traded $
        return w_achieved, float(cost_usd.sum() / aum)

    def carry(self, w_held, days=1):
        w = np.asarray(w_held, float)
        short_notional = float(np.abs(np.minimum(w, 0.0)).sum())          # fraction of NAV held short
        leverage_excess = max(float(np.abs(w).sum()) - 1.0, 0.0)          # gross above 1x
        daily = (short_notional * self.borrow_bps + leverage_excess * self.financing_bps) / 1e4 / TRADING_DAYS
        return daily * days
