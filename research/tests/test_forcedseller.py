"""Tests for the forced-seller module — the vol-control reaction function, the forced-flow signal, the
predictability regression, and the engine strategies."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import forcedseller as fs


def _spy(n=500, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    return pd.DataFrame({"SPY": 100 * np.cumprod(1 + rng.normal(0.0004, 0.011, n))}, index=idx)


def test_target_exposure_is_inverse_vol_and_capped():
    rvol = pd.Series([0.10, 0.15, 0.30, 0.01])
    e = fs.target_exposure(rvol, target_vol=0.15, max_lev=2.0)
    assert abs(e.iloc[0] - 1.5) < 1e-9 and abs(e.iloc[1] - 1.0) < 1e-9   # target/vol
    assert e.iloc[2] < e.iloc[1]                                          # higher vol → lower exposure
    assert e.iloc[3] == 2.0                                               # capped at max_lev


def test_forced_flow_is_negative_when_vol_spikes():
    # Vol jumps up over the window → exposure falls → forced flow (Δexposure) is negative (deleveraging).
    rvol = pd.Series([0.10] * 10 + [0.25] * 10)
    flow = fs.forced_flow(fs.target_exposure(rvol), lookback=5)
    assert flow.iloc[12] < 0


def test_flow_signal_is_bounded():
    sig = fs.flow_signal(_spy()["SPY"].pct_change()).dropna()
    assert sig.abs().max() <= 1.0 + 1e-9


def test_forward_predictability_runs():
    r = _spy()["SPY"].pct_change()
    out = fs.forward_predictability(r, fs.flow_signal(r), horizons=(1, 5))
    assert set(out["horizon"]) == {1, 5} and "t_stat" in out.columns


def test_strategies_run_through_the_engine():
    prices = _spy()
    for strat in (fs.ForcedSeller(), fs.VolTargetHold(), fs.BuyHold()):
        r = eng.run(strat, prices, eng.BacktestConfig(rebalance=1, cost_bps=1.0))
        assert np.isfinite(r.stats["sharpe"]) and r.stats["n_days"] > 100


def test_forced_seller_can_go_short_but_voltarget_hold_stays_long():
    prices = _spy()
    fseller = eng.run(fs.ForcedSeller(), prices, eng.BacktestConfig(rebalance=1, cost_bps=0.0))
    vhold = eng.run(fs.VolTargetHold(), prices, eng.BacktestConfig(rebalance=1, cost_bps=0.0))
    assert (fseller.weights["SPY"] < 0).any()          # the flow signal takes short positions
    assert (vhold.weights["SPY"] >= 0).all()           # vol-target-hold is long-only
