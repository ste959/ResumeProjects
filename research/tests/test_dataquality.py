"""Tests for the data-quality audit — it catches the artifacts that fake alpha (stale prices, unadjusted
splits, missing history) and gates a study on clean inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import dataquality as dq


def _clean_panel(n=300, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    return pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, (n, 3)), axis=0),
                        index=idx, columns=["A", "B", "C"])


def test_clean_panel_passes():
    rep = dq.audit_prices(_clean_panel())
    assert rep["summary"]["clean"] is True and rep["summary"]["n_flagged"] == 0


def test_stale_prices_are_flagged():
    p = _clean_panel()
    p.iloc[50:60, 0] = p.iloc[50, 0]                 # 10-day flat run in A (a dead/stale feed)
    rep = dq.audit_prices(p)
    assert rep["by_symbol"]["A"]["max_stale_run"] >= 5 and rep["by_symbol"]["A"]["flag"]


def test_unadjusted_split_jump_is_flagged():
    p = _clean_panel()
    p.iloc[100:, 1] = p.iloc[100:, 1] * 0.5          # a 2:1 split left unadjusted → a −50% one-day jump
    rep = dq.audit_prices(p)
    assert rep["by_symbol"]["B"]["extreme_jumps"] >= 1 and rep["by_symbol"]["B"]["flag"]


def test_low_coverage_is_flagged():
    p = _clean_panel()
    p.iloc[:200, 2] = np.nan                          # C only has the last third of history
    rep = dq.audit_prices(p)
    assert rep["by_symbol"]["C"]["coverage"] < 0.9 and rep["by_symbol"]["C"]["flag"]


def test_assert_clean_raises_on_dirty_data():
    p = _clean_panel()
    p.iloc[100:, 0] = p.iloc[100:, 0] * 0.5          # inject a split jump
    try:
        dq.assert_clean(p)
        assert False, "should have raised"
    except ValueError:
        pass
