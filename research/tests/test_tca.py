"""Tests for transaction-cost analysis — the implementation-shortfall decomposition is additive and
responds to liquidity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import execution as ex
from mds import strategies_lib as sl
from mds import tca


def _panel(n=700, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    rets = rng.normal([0.0005, -0.0004, 0.0003, 0.0], [0.01, 0.012, 0.008, 0.02], size=(n, 4))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=["SPY", "IEF", "LQD", "GLD"])


def _liq(index, cols, adv):
    mk = lambda v: pd.DataFrame(v, index=index, columns=cols)
    return ex.Liquidity(adv_usd=mk(adv), daily_vol=mk(0.01), spread_frac=mk(5e-4))


def test_shortfall_decomposition_is_additive():
    prices = _panel()
    liq = _liq(prices.index, list(prices.columns), adv=5e8)
    s = tca.implementation_shortfall(sl.TimeSeriesMomentum(list(prices.columns)), prices, liq, aum=1e8)
    # execution + opportunity must reconstruct the total shortfall exactly.
    assert abs(s["execution_cost_annual"] + s["opportunity_cost_annual"] - s["total_shortfall_annual"]) < 1e-9
    for k in ("ideal_sharpe", "realistic_sharpe", "realistic_avg_gross"):
        assert np.isfinite(s[k])


def test_thinner_market_costs_more_to_execute():
    prices = _panel()
    strat = sl.TimeSeriesMomentum(list(prices.columns))
    thick = tca.implementation_shortfall(strat, prices, _liq(prices.index, list(prices.columns), 1e10),
                                         aum=1e9)
    thin = tca.implementation_shortfall(strat, prices, _liq(prices.index, list(prices.columns), 1e7),
                                        aum=1e9)
    # Same AUM, thinner ADV → larger total implementation shortfall (spread/impact + opportunity).
    assert thin["total_shortfall_annual"] >= thick["total_shortfall_annual"]
