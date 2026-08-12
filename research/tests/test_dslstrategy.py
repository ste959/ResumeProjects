"""Tests for the DSL→engine bridge: a compiled signal runs as a real strategy, is dollar-neutral and
unit-gross, and — critically — is causal (a weight never depends on future prices)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds.dslstrategy import DslStrategy


def _prices(seed, cols=("A", "B", "C", "D", "E"), n=140):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    steps = rng.normal(0, 0.01, size=(n, len(cols)))
    return pd.DataFrame(100 * np.exp(np.cumsum(steps, axis=0)), index=idx, columns=list(cols))


def test_runs_through_the_engine_and_produces_a_net_series():
    px = _prices(0)
    strat = DslStrategy("zscore(-ts_delta(close, 5))", list(px.columns), warmup=20)
    result = eng.run(strat, px, eng.BacktestConfig(rebalance=5))
    assert isinstance(result, eng.StrategyResult)
    assert len(result.net) > 0
    assert "sharpe" in result.stats


def test_weights_are_dollar_neutral_and_unit_gross():
    px = _prices(1)
    strat = DslStrategy("zscore(ts_delta(close, 10))", list(px.columns), warmup=20)
    strat.prepare(px[strat.symbols()])
    w = strat.target_weights(px, 60)
    assert abs(w.sum()) < 1e-9                 # dollar-neutral
    assert abs(np.abs(w).sum() - 1.0) < 1e-9   # unit gross


def test_signal_is_causal_future_prices_do_not_change_past_weights():
    px = _prices(2)
    t = 60
    future_perturbed = px.copy()
    future_perturbed.iloc[t:] *= 1.5           # change everything from t onward

    a = DslStrategy("zscore(ts_mean(close, 15))", list(px.columns), warmup=20)
    b = DslStrategy("zscore(ts_mean(close, 15))", list(px.columns), warmup=20)
    a.prepare(px[a.symbols()])
    b.prepare(future_perturbed[b.symbols()])

    wa = a.target_weights(px, t)               # uses the signal at row t-1
    wb = b.target_weights(future_perturbed, t)
    assert np.allclose(wa, wb, atol=1e-12)     # identical: t-1 data is untouched
