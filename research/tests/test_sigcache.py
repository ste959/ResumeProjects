"""Tests for the content-addressed signal cache.

The cache must be *transparent* (a cached result equals the freshly-evaluated one), and its
invalidation must be *precise*: changing a column a signal reads is a miss, changing an unrelated
column is still a hit. And it must persist across process boundaries (a fresh cache instance pointed at
the same directory finds the earlier result).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mds import alphadsl as dsl
from mds.sigcache import SignalCache


def _panel(seed, cols=("A", "B", "C", "D", "E"), n=120):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n)
    return pd.DataFrame(rng.normal(size=(n, len(cols))), index=idx, columns=list(cols))


@pytest.fixture
def env():
    return {"close": _panel(0) + 100, "volume": _panel(1).abs() + 1}


@pytest.fixture
def cache(tmp_path):
    return SignalCache(tmp_path / "sigcache")


def _same(a, b):
    return np.allclose(a.values, b.values, equal_nan=True) and a.index.equals(b.index) \
        and list(a.columns) == list(b.columns)


def test_cache_is_transparent(cache, env):
    src = "zscore(ts_delta(close, 5))"
    direct = dsl.evaluate(src, env)
    cached = cache.evaluate(src, env)
    assert _same(direct, cached)


def test_second_call_hits_without_recomputing(cache, env):
    src = "rank(ts_mean(close, 10))"
    cache.evaluate(src, env)
    cache.evaluate(src, env)
    assert cache.stats["misses"] == 1          # computed exactly once
    assert cache.stats["hits"] == 1


def test_changing_a_used_column_invalidates(cache, env):
    src = "zscore(close)"
    cache.evaluate(src, env)
    env2 = {**env, "close": env["close"] * 1.01}    # the column this signal reads changed
    cache.evaluate(src, env2)
    assert cache.stats["misses"] == 2               # a genuine recompute


def test_changing_an_unrelated_column_still_hits(cache, env):
    src = "zscore(close)"                            # reads close, not volume
    cache.evaluate(src, env)
    env2 = {**env, "volume": env["volume"] * 5.0}   # unrelated column changed
    cache.evaluate(src, env2)
    assert cache.stats["misses"] == 1               # no recompute — volume isn't an input here
    assert cache.stats["hits"] == 1


def test_whitespace_only_change_is_the_same_key(cache, env):
    cache.evaluate("zscore( close )", env)
    cache.evaluate("zscore(close)", env)            # same AST → same fingerprint → same key
    assert cache.stats["misses"] == 1


def test_persists_to_disk_across_instances(tmp_path, env):
    src = "ts_std(close, 20)"
    c1 = SignalCache(tmp_path / "c")
    first = c1.evaluate(src, env)
    assert c1.stats["writes"] == 1

    c2 = SignalCache(tmp_path / "c")                # fresh instance, empty memory tier
    second = c2.evaluate(src, env)
    assert c2.stats["disk_hits"] == 1              # found the earlier result on disk
    assert c2.stats["misses"] == 0
    assert _same(first, second)


def test_clear_forces_recompute(cache, env):
    src = "zscore(close)"
    cache.evaluate(src, env)
    cache.clear()
    cache.evaluate(src, env)
    assert cache.stats["misses"] == 2
