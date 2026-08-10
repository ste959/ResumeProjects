"""Tests for the strategy engine SDK (`mds/engine.py`, the platform spine) — the execution contract
(causality, cost, leverage cap), the compare/gauntlet wiring, attribution reconciliation, and the
tearsheet shape. Also checks that a ported strategy runs end-to-end through the SDK.

(Distinct from tests/test_engine.py, which covers the *live* order-submission engine in `service/`.)"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import strategies_lib as sl


def _panel(n_days: int = 700, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-01", periods=n_days, freq="B")
    drifts = np.array([0.0005, -0.0004, 0.0003, 0.0])
    vols = np.array([0.010, 0.012, 0.008, 0.020])
    cols = ["SPY", "IEF", "LQD", "GLD"]
    rets = rng.normal(drifts, vols, size=(n_days, len(cols)))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=dates, columns=cols)


class _Const(eng.Strategy):
    """A fixed-weight strategy, for testing the engine mechanics independently of any signal."""
    name = "const"
    warmup = 30

    def __init__(self, w):
        self._w = np.asarray(w, float)

    def symbols(self):
        return ["SPY", "IEF", "LQD", "GLD"]

    def target_weights(self, prices, t):
        return self._w


def test_run_produces_aligned_net_and_weights():
    r = eng.run(_Const([0.25, 0.25, 0.25, 0.25]), _panel())
    assert isinstance(r, eng.StrategyResult)
    assert len(r.net) == len(r.weights) and r.stats["n_days"] == len(r.net)
    assert list(r.weights.columns) == ["SPY", "IEF", "LQD", "GLD"]


def test_engine_has_no_lookahead():
    # Truncating future data must not change any past net value (weights use only prices.iloc[:t]).
    prices = _panel(700)
    full = eng.run(sl.RiskParity(["SPY", "IEF", "LQD", "GLD"], lookback=252), prices).net
    trunc = eng.run(sl.RiskParity(["SPY", "IEF", "LQD", "GLD"], lookback=252), prices.iloc[:450]).net
    common = trunc.index[:100]
    assert np.allclose(full.loc[common].to_numpy(), trunc.loc[common].to_numpy(), atol=1e-12)


def test_higher_cost_never_helps():
    prices = _panel()
    cheap = eng.run(sl.TimeSeriesMomentum(["SPY", "IEF", "LQD", "GLD"]), prices,
                    eng.BacktestConfig(cost_bps=1.0)).stats["ann_return"]
    dear = eng.run(sl.TimeSeriesMomentum(["SPY", "IEF", "LQD", "GLD"]), prices,
                   eng.BacktestConfig(cost_bps=50.0)).stats["ann_return"]
    assert dear <= cheap + 1e-9


def test_leverage_cap_binds():
    # A strategy asking for 5x gross must be capped to max_leverage.
    r = eng.run(_Const([2.0, 2.0, 0.5, 0.5]), _panel(), eng.BacktestConfig(max_leverage=3.0))
    assert r.avg_gross <= 3.0 + 1e-9


def test_compare_runs_everything_through_one_gauntlet():
    prices = _panel()
    syms = ["SPY", "IEF", "LQD", "GLD"]
    out = eng.compare([sl.EqualWeight(syms), sl.RiskParity(syms), sl.TimeSeriesMomentum(syms)], prices)
    assert len(out["results"]) == 3
    assert out["gauntlet"]["n_strategies"] == 3
    assert {"best", "deflated_sharpe", "pbo", "bonferroni_t"} <= set(out["gauntlet"])


def test_attribution_reconciles_to_net_at_zero_cost():
    prices = _panel()
    r = eng.run(_Const([0.25, 0.25, 0.25, 0.25]), prices, eng.BacktestConfig(cost_bps=0.0))
    at = eng.attribution(r, prices, groups={"SPY": "Eq", "IEF": "Bond", "LQD": "Bond", "GLD": "Real"})
    assert abs(at["per_asset"].sum() - r.net.sum()) < 1e-9
    assert set(at["per_group"].index) <= {"Eq", "Bond", "Real"}


def test_tearsheet_has_the_standard_sections():
    ts = eng.tearsheet(eng.run(_Const([0.25, 0.25, 0.25, 0.25]), _panel()))
    assert set(ts) == {"name", "performance", "tail", "activity"}
    assert {"ann_return", "sharpe", "max_drawdown"} <= set(ts["performance"])


def test_ported_strategy_matches_a_hand_equal_weight():
    # EqualWeight through the SDK should equal a hand-rolled 1/N net (same execution, no signal drift).
    prices = _panel()
    sdk = eng.run(sl.EqualWeight(["SPY", "IEF", "LQD", "GLD"]), prices,
                  eng.BacktestConfig(cost_bps=0.0)).net
    hand = eng.run(_Const([0.25, 0.25, 0.25, 0.25]), prices, eng.BacktestConfig(cost_bps=0.0)).net
    common = sdk.index.intersection(hand.index)   # warmups differ → compare on the overlap
    assert np.allclose(sdk.loc[common].to_numpy(), hand.loc[common].to_numpy(), atol=1e-12)
