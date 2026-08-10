"""Diversified market-neutral multi-factor equity book — the honest institutional shot at a real edge.

No single factor is reliable, and on liquid mega-caps each is thin or decayed. But the frontier the new
long-history + broad-universe data unlocks is the one AQR/DFA actually run at scale: a **diversified,
market-neutral, capacity-aware multi-factor portfolio**. Two forces now favor it — 20 years of data
(min-detectable Sharpe ≈ 0.6, so a modest real premium is finally detectable) and breadth (IR = IC·√breadth).

The factors here are **price-only** (robust across 20 years and hundreds of names, no fundamental-data
quality risk), documented, and economically grounded:
  • **Momentum (12–1)** — under-reaction + a risk premium (Jegadeesh–Titman).
  • **Low-volatility / BAB** — leverage-constrained investors overpay for high-β "lottery" names, leaving
    low-β under-priced (Frazzini–Pedersen). Robust and **low-turnover → capacity-friendly**.
  • **Short-term reversal** — compensation for providing liquidity (optional; higher turnover).

`MultiFactorBook` subclasses `ImplementedMomentum`, so the composite z-score signal flows through the *whole*
deployment stack for free — characteristic neutralization, market-beta hedge, vol-targeting, turnover
control, and the factor-risk-model optimizer. Honest caveat: the yfinance universe is **survivorship-biased**
(current names), which inflates factor returns — disclosed, and partly mitigated by the long/short structure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import implement as im


def momentum(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """12–1 momentum: trailing return skipping the last month."""
    return prices.shift(skip) / prices.shift(lookback) - 1.0


def low_volatility(prices: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """Low-volatility factor = −(trailing realized volatility): long low-vol, short high-vol."""
    return -(prices.pct_change().rolling(window).std())


def short_reversal(prices: pd.DataFrame, window: int = 21) -> pd.DataFrame:
    """Short-term reversal = −(last-month return): long recent losers, short recent winners."""
    return -(prices / prices.shift(window) - 1.0)


def _xs_z(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score each date (standardize across names) so factors combine on one scale."""
    mu, sd = df.mean(axis=1), df.std(axis=1).replace(0, np.nan)
    return df.sub(mu, axis=0).div(sd, axis=0)


_FACTORS = {"mom": momentum, "lowvol": low_volatility, "rev": short_reversal}


class MultiFactorBook(im.ImplementedMomentum):
    """A composite of z-scored price factors, run through the full `ImplementedMomentum` deployment stack.
    `factors` selects which to blend (equal-weight z). Everything else — neutralize / hedge / risk / optimize
    — is inherited, so this *is* the institutional book: market-neutral, capacity-aware, risk-managed."""
    name = "multifactor"

    def __init__(self, stocks: list[str], factors: tuple[str, ...] = ("mom", "lowvol"), **kw):
        super().__init__(stocks, **kw)
        self.factors = factors
        self.name = "+".join(factors)

    def prepare(self, prices: pd.DataFrame) -> None:
        super().prepare(prices)                                        # sets _rets, _vol, _beta, _mom(mom-only)
        px = prices[self._stocks]
        comps = [_xs_z(_FACTORS[f](px)) for f in self.factors]
        composite = sum(comps) / len(comps)                            # equal-weight z-score blend
        self._mom = composite                                          # override the signal with the composite
        self._mom_smooth = composite.ewm(halflife=self.smooth_hl).mean()
