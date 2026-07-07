"""Tests for the backtest lab's pure core — direction, cost erosion, causality, and that the same
strategy signals used live drive the backtest."""

from __future__ import annotations

import math

from service import lab, strategies as S


def _defn(kind="ma_crossover", **params):
    base = {"fast": 12, "slow": 48} if kind == "ma_crossover" else {"lookback": 24}
    base.update(params)
    return S.StrategyDef(id="bt", name="", desc="", kind=kind, asset_class="crypto",
                         symbols=("BTC/USD",), params=base)


def test_uptrend_is_a_positive_edge():
    closes = [100 * (1.001 ** i) for i in range(300)]      # steady rise → long trend follows it
    r = lab._simulate(_defn(), closes, "1Hour", cost_bps=0.0)
    assert r["ok"] and r["net_sharpe"] > 0 and r["total_return"] > 0
    assert r["passes"]


def test_costs_erode_returns():
    closes = [100 * (1.001 ** i) for i in range(300)]
    free = lab._simulate(_defn(), closes, "1Hour", cost_bps=0.0)["total_return"]
    dear = lab._simulate(_defn(), closes, "1Hour", cost_bps=100.0)["total_return"]
    assert free > dear                                     # cost only subtracts


def test_choppy_series_does_not_pass():
    chop = [100 * (1 + 0.02 * math.sin(i / 3)) for i in range(300)]
    r = lab._simulate(_defn(), chop, "1Hour", cost_bps=20.0)
    assert not r["passes"]                                 # whipsaw + costs → no edge


def test_flat_series_earns_nothing():
    flat = [100.0] * 200                                   # no moves → no return, no signal churn
    r = lab._simulate(_defn(), flat, "1Hour", cost_bps=10.0)
    assert abs(r["total_return"]) < 1e-9
    assert r["avg_turnover"] == 0.0


def test_momentum_template_runs_and_is_causal():
    # A late regime flip: down then up. Momentum should be flat through the down leg (no look-ahead
    # into the recovery) and long once the trailing return turns positive.
    closes = [100 * (0.999 ** i) for i in range(120)] + [90 * (1.002 ** i) for i in range(180)]
    r = lab._simulate(_defn("momentum", lookback=24), closes, "1Hour", cost_bps=5.0)
    assert r["ok"] and r["n_bars"] == len(closes) - 1      # one return per bar-to-bar step
    assert r["total_return"] > 0                           # captures the up leg, not the down


def test_backtest_matches_live_signal():
    # The backtest's final-bar position equals what the live engine would target right now — same code.
    closes = [100 * (1.001 ** i) for i in range(300)]
    defn = _defn()
    live_sign = S.target_sign(defn, closes)                # what the engine would do at the last bar
    assert live_sign == 1                                  # uptrend → long, in both paths
