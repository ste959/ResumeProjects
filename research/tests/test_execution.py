"""Tests for execution & cost realism — the Corwin–Schultz spread estimator, the flat vs. realistic
cost models (spread + square-root impact + participation cap/partial fills + borrow/financing carry),
and the capacity curve (edge decays with size)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import execution as ex
from mds import strategies_lib as sl


def _dates(n):
    return pd.date_range("2021-01-01", periods=n, freq="B")


def _liq(index, cols, adv=1e6, vol=0.01, spread=5e-4):
    mk = lambda v: pd.DataFrame(v, index=index, columns=cols)
    return ex.Liquidity(adv_usd=mk(adv), daily_vol=mk(vol), spread_frac=mk(spread))


# ── spread estimator ──────────────────────────────────────────────────────────────────────────────
def test_corwin_schultz_is_nonnegative_and_finite():
    idx = _dates(300)
    rng = np.random.default_rng(0)
    mid = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0, 0.01, (300, 2)), axis=0), index=idx, columns=["A", "B"])
    high, low = mid * 1.004, mid * 0.996           # a ~0.8% high-low band
    s = ex.corwin_schultz_spread(high, low).dropna()
    assert (s.to_numpy() >= 0).all() and np.isfinite(s.to_numpy()).all()


def test_wider_range_gives_a_larger_spread_estimate():
    idx = _dates(300)
    base = pd.DataFrame(100.0, index=idx, columns=["X"])
    narrow = ex.corwin_schultz_spread(base * 1.002, base * 0.998).dropna().mean().iloc[0]
    wide = ex.corwin_schultz_spread(base * 1.02, base * 0.98).dropna().mean().iloc[0]
    assert wide > narrow


def test_adv_spread_shrinks_for_more_liquid_names_and_is_clipped():
    idx = _dates(10)
    adv = pd.DataFrame({"liquid": [3e10] * 10, "thin": [2e8] * 10}, index=idx)   # $30B vs $200M ADV
    s = ex.adv_spread(adv)
    assert s["liquid"].iloc[0] < s["thin"].iloc[0]         # more volume → tighter spread
    assert (s.to_numpy() >= 5e-5 - 1e-12).all() and (s.to_numpy() <= 2.5e-3 + 1e-12).all()  # clipped


# ── flat vs realistic ─────────────────────────────────────────────────────────────────────────────
def test_flat_bps_fills_at_target():
    m = ex.FlatBps(10.0)
    w_ach, cost = m.rebalance(np.zeros(3), np.array([0.5, 0.3, 0.2]), 1e8, None)
    assert np.allclose(w_ach, [0.5, 0.3, 0.2])
    assert abs(cost - 1.0 * 10 / 1e4) < 1e-12       # turnover 1.0 × 10bps


def test_realistic_requires_liquidity():
    m = ex.RealisticExecution()
    try:
        m.rebalance(np.zeros(2), np.array([0.5, 0.5]), 1e8, None)
        assert False, "should have raised without liquidity"
    except ValueError:
        pass


def test_participation_cap_causes_partial_fills():
    # AUM huge relative to ADV → the desired trade can't fill; achieved barely moves from prior.
    m = ex.RealisticExecution(max_participation=0.10)
    liq = {"adv": np.array([1e6, 1e6]), "vol": np.array([0.01, 0.01]), "spread": np.array([5e-4, 5e-4])}
    w_ach, cost = m.rebalance(np.zeros(2), np.array([0.5, 0.5]), aum=1e9, liq=liq)
    assert (np.abs(w_ach) < 0.5).all()              # nowhere near target — capacity-constrained
    assert (np.abs(w_ach) <= 0.10 * 1e6 / 1e9 + 1e-12).all()   # capped at max_participation × ADV / AUM


def test_impact_cost_rises_with_trade_size():
    m = ex.RealisticExecution(max_participation=1.0)   # no cap, so bigger trades really fill and cost more
    liq = {"adv": np.array([1e9]), "vol": np.array([0.02]), "spread": np.array([5e-4])}
    _, small = m.rebalance(np.zeros(1), np.array([0.01]), aum=1e8, liq=liq)
    _, big = m.rebalance(np.zeros(1), np.array([0.20]), aum=1e8, liq=liq)
    assert big > small                                # square-root impact ⇒ larger trade, larger cost/$


def test_carry_charges_shorts_and_leverage_but_not_a_long_only_book():
    m = ex.RealisticExecution(borrow_bps=50, financing_bps=100)
    assert m.carry(np.array([0.6, 0.4])) == 0.0                # long-only, gross 1 → no carry
    assert m.carry(np.array([-0.5, 0.5])) > 0.0                # short leg pays borrow
    assert m.carry(np.array([1.0, 1.0])) > 0.0                 # gross 2 → financing on the excess


# ── engine integration + capacity ─────────────────────────────────────────────────────────────────
def _panel(n=700, seed=0):
    rng = np.random.default_rng(seed)
    idx = _dates(n)
    rets = rng.normal([0.0005, -0.0004, 0.0003, 0.0], [0.01, 0.012, 0.008, 0.02], size=(n, 4))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=["SPY", "IEF", "LQD", "GLD"])


def test_engine_runs_with_realistic_execution():
    prices = _panel()
    liq = _liq(prices.index, list(prices.columns), adv=5e8)
    r = eng.run(sl.TimeSeriesMomentum(list(prices.columns)), prices,
                eng.BacktestConfig(execution=ex.RealisticExecution(), aum=1e7), liquidity=liq)
    assert np.isfinite(r.stats["sharpe"]) and r.stats["n_days"] > 100


def test_capacity_curve_shrinks_the_book_at_scale():
    # In a thin market, a larger AUM can't fill its target → the achieved book is smaller (under-invested).
    prices = _panel()
    liq = _liq(prices.index, list(prices.columns), adv=2e6)   # deliberately illiquid
    strat = sl.TimeSeriesMomentum(list(prices.columns))
    small = eng.run(strat, prices, eng.BacktestConfig(execution=ex.RealisticExecution(), aum=1e6), liq)
    huge = eng.run(strat, prices, eng.BacktestConfig(execution=ex.RealisticExecution(), aum=1e9), liq)
    assert huge.avg_gross < small.avg_gross          # capacity-constrained at size
