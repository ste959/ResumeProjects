"""Tests for the alpha-decay / crowding monitor — it detects a decaying edge, calls a stable one stable,
estimates a half-life, and flags rising crowding."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import decaymonitor as dm


def _series(daily, n, seed=0):
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    return pd.Series(daily(np.random.default_rng(seed), n), index=idx)


def test_bucketed_sharpe_returns_the_buckets():
    net = _series(lambda r, n: r.normal(0.0004, 0.01, n), 600)
    b = dm.bucketed_sharpe(net, n_buckets=6)
    assert len(b) == 6 and {"bucket", "sharpe", "n_days"} <= set(b.columns)


def test_performance_trend_detects_decay():
    # Strong positive drift in the first half, ~zero in the second → a downward Sharpe trend.
    n = 800
    rng = np.random.default_rng(2)
    r = np.concatenate([rng.normal(0.0012, 0.01, n // 2), rng.normal(0.0, 0.01, n // 2)])
    net = pd.Series(r, index=pd.date_range("2019-01-01", periods=n, freq="B"))
    trend = dm.performance_trend(net, n_buckets=6)
    assert trend["slope"] < 0 and trend["t_stat"] < 0             # decaying
    rep = dm.decay_report(net)
    assert "DECAY" in rep["verdict"].upper()
    assert rep["sharpe_first_half"] > rep["sharpe_second_half"]


def test_half_life_is_finite_when_decaying_and_inf_when_stable():
    n = 800
    rng = np.random.default_rng(3)
    decaying = pd.Series(np.concatenate([rng.normal(0.0015, 0.01, n // 2), rng.normal(0.0001, 0.01, n // 2)]),
                         index=pd.date_range("2019-01-01", periods=n, freq="B"))
    stable = _series(lambda r, m: r.normal(0.0005, 0.01, m), n, seed=4)
    assert np.isfinite(dm.half_life(decaying))
    assert dm.half_life(stable) == float("inf")


def test_crowding_trend_flags_rising_correlation_to_a_factor():
    n = 800
    rng = np.random.default_rng(5)
    factor = rng.normal(0, 0.01, n)
    w = np.linspace(0.0, 1.0, n)                                  # the strategy loads more on the factor over time
    strat = w * factor + (1 - w) * rng.normal(0, 0.01, n)
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    c = dm.crowding_trend(pd.Series(strat, index=idx), pd.Series(factor, index=idx))
    assert c["corr_slope"] > 0 and c["t_stat"] > 0               # correlation to the factor is rising


def test_ic_decay_detects_a_fading_signal():
    n = 300
    ic = pd.Series(np.linspace(0.05, -0.01, n) + np.random.default_rng(6).normal(0, 0.005, n),
                   index=pd.date_range("2019-01-01", periods=n, freq="B"))
    d = dm.ic_decay(ic)
    assert d["slope"] < 0 and d["first"] > d["last"]
