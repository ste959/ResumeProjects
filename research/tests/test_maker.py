"""Tests for the maker-execution model — the properties that make the spread-vs-adverse-selection
decomposition trustworthy: markouts are correct, a two-sided maker is adversely selected on a trend,
and the signal-split rewards a genuinely predictive signal."""

from __future__ import annotations

import numpy as np

from mds import maker


def test_markout_bps_measures_forward_move():
    mid = np.array([100.0, 101.0, 102.0, 103.0])
    mo = maker.markout_bps(mid, 1)
    assert abs(mo[0] - (101.0 / 100.0 - 1.0) * 1e4) < 1e-6   # +~99.5 bps
    assert np.isnan(mo[-1])                                   # no future for the last point


def test_two_sided_maker_earns_spread_but_is_adversely_selected_on_a_downtrend():
    n = 200
    mid = 100.0 * np.exp(-0.001 * np.arange(n))               # steadily falling
    spr = np.full(n, 2.0)                                     # 2 bps spread → 1 bp half-spread
    r = maker.maker_backtest(mid, spr, inv_cap=100, markout_h=5)
    assert r["n_fills"] > 0
    assert abs(r["spread_bps"] - 1.0) < 1e-6                  # earns the half-spread on every fill
    assert r["adverse_bps"] < 0                               # bought into the decline → adverse
    assert r["net_bps"] < r["spread_bps"]                     # adverse selection eats into the spread


def test_signal_split_rewards_a_predictive_signal():
    rng = np.random.default_rng(0)
    n = 3000
    mid = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    spr = np.full(n, 2.0)
    r = maker.maker_backtest(mid, spr, inv_cap=5, markout_h=10)
    # An ORACLE signal = the sign of the forward markout (cheating, only to prove the split works):
    # fills it endorses should dodge adverse selection and net more than the ones it warns against.
    oracle = np.nan_to_num(maker.markout_bps(mid, 10))
    split = maker.signal_split(r, oracle)
    assert split["aligned_fills"] > 0 and split["contra_fills"] > 0
    assert split["aligned_net_bps"] > split["contra_net_bps"]
