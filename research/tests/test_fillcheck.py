"""Tests for the fill-validation analytics — realized spread, implementation shortfall, round-trip cost,
and model calibration. All network-free."""

from __future__ import annotations

import numpy as np

from mds import fillcheck as fc


def test_realized_spread_is_proportional():
    assert abs(fc.realized_spread(99.95, 100.05) - (0.10 / 100.0)) < 1e-9


def test_implementation_shortfall_signs_costs_correctly():
    # A buy that fills above the mid is a cost; a sell that fills below the mid is a cost.
    assert fc.implementation_shortfall(100.05, 100.0, "buy") > 0
    assert fc.implementation_shortfall(99.95, 100.0, "sell") > 0
    assert fc.implementation_shortfall(100.0, 100.0, "buy") == 0.0     # fill at mid → no cost


def test_roundtrip_cost_recovers_the_crossed_spread():
    # Cross to the ask (100.05) on the buy, to the bid (99.95) on the sell, mid 100 both times →
    # round-trip cost ≈ the full 10 bps spread.
    rt = fc.roundtrip_cost(buy_fill=100.05, buy_mid=100.0, sell_fill=99.95, sell_mid=100.0)
    assert abs(rt - 0.001) < 1e-9


def test_calibration_factor():
    assert fc.calibration(realized=0.0003, modeled=0.0005) == 0.6      # model was 1.67× conservative
    assert np.isnan(fc.calibration(0.0003, 0.0))


def test_summarize_aggregates_and_calibrates():
    rows = [{"realized_bps": 3.0, "modeled_bps": 5.0}, {"realized_bps": 4.0, "modeled_bps": 5.0}]
    s = fc.summarize(rows)
    assert s["n"] == 2 and s["mean_realized_bps"] == 3.5 and s["calibration"] == 0.7
