"""Tests for the parallel research runner.

The properties that matter for a parallel component: it computes the *same* answer as the serial path,
that answer is *independent of the worker count* (no scheduler dependence), and a single failing task
is *isolated* rather than taking down the batch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import alphadsl as dsl
from mds import engine as eng
from mds.dslstrategy import DslStrategy
from mds.parallel import backtest_signals, evaluate_signals
from mds.sigcache import SignalCache


def _prices(seed=0, cols=("A", "B", "C", "D", "E"), n=160):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    steps = rng.normal(0.0003, 0.011, size=(n, len(cols)))
    return pd.DataFrame(100 * np.exp(np.cumsum(steps, axis=0)), index=idx, columns=list(cols))


def _env():
    close = _prices()
    return {"close": close, "returns": close.pct_change(),
            "volume": (_prices(9).abs() + 1)}


SIGNALS = [
    "zscore(-ts_delta(close, 5))",
    "rank(ts_mean(close, 20))",
    "zscore(ts_std(returns, 20))",
    "demean(ts_delta(close, 10))",
]


def _same(a, b):
    return np.allclose(a.values, b.values, equal_nan=True) and list(a.columns) == list(b.columns)


def test_evaluate_signals_matches_direct_evaluation():
    env = _env()
    results = evaluate_signals(SIGNALS, env, max_workers=2)
    assert [r.signal for r in results] == SIGNALS          # input order preserved
    for r in results:
        assert r.ok
        assert _same(r.panel, dsl.evaluate(r.signal, env))


def test_results_are_independent_of_worker_count():
    env = _env()
    one = evaluate_signals(SIGNALS, env, max_workers=1)
    two = evaluate_signals(SIGNALS, env, max_workers=2)
    for a, b in zip(one, two):
        assert a.signal == b.signal and _same(a.panel, b.panel)


def test_evaluate_isolates_a_failing_signal():
    env = _env()
    signals = ["zscore(close)", "rank(price)", "ts_mean(close, 10)"]   # 'price' isn't in env
    results = evaluate_signals(signals, env, max_workers=2)
    ok = {r.signal: r.ok for r in results}
    assert ok == {"zscore(close)": True, "rank(price)": False, "ts_mean(close, 10)": True}
    bad = next(r for r in results if not r.ok)
    assert "price" in bad.error


def test_evaluate_signals_shares_a_cache(tmp_path):
    env = _env()
    cache = SignalCache(tmp_path / "c")
    results = evaluate_signals(SIGNALS, env, max_workers=2, cache=cache)
    assert all(r.ok for r in results)
    # Re-running in-process now hits the shared on-disk store the workers populated.
    assert cache.evaluate(SIGNALS[0], env) is not None
    assert cache.stats["disk_hits"] >= 1


def test_backtest_signals_matches_serial_engine():
    px = _prices()
    signals = {"reversal": "zscore(-ts_delta(close, 5))", "momentum": "zscore(ts_delta(close, 60))"}
    summ = backtest_signals(signals, px, config=eng.BacktestConfig(rebalance=5),
                            warmup=20, max_workers=2)
    by_name = {s["name"]: s for s in summ}
    for name, expr in signals.items():
        strat = DslStrategy(expr, list(px.columns), warmup=20)
        r = eng.run(strat, px, eng.BacktestConfig(rebalance=5))
        assert by_name[name]["ok"]
        assert abs(by_name[name]["sharpe"] - r.stats["sharpe"]) < 1e-9


def test_backtest_isolates_a_failing_signal():
    px = _prices()
    signals = {"good": "zscore(ts_delta(close, 5))", "bad": "zscore(nonexistent_col)"}
    summ = {s["name"]: s for s in backtest_signals(signals, px, warmup=20, max_workers=2)}
    assert summ["good"]["ok"] and not summ["bad"]["ok"]
