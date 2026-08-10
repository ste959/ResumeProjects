"""Tests for the reporting layer — the HTML tearsheet and leaderboard render, are self-contained (no
external resources), and include the expected sections."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import report as rp
from mds import strategies_lib as sl


def _panel(n=700, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    rets = rng.normal([0.0005, -0.0003, 0.0003, 0.0], [0.01, 0.012, 0.008, 0.02], size=(n, 4))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=["SPY", "IEF", "LQD", "GLD"])


def test_sparkline_renders_svg_and_handles_short_series():
    svg = rp._sparkline([1.0, 1.1, 1.05, 1.2])
    assert svg.startswith("<svg") and "polyline" in svg
    assert rp._sparkline([1.0]).startswith("<svg")          # degenerate input doesn't crash


def test_tearsheet_is_self_contained_html_with_sections():
    prices = _panel()
    res = eng.run(sl.RiskParity(list(prices.columns)), prices, eng.BacktestConfig(cost_bps=5.0))
    html = rp.tearsheet_html(res, prices, sleeves={"SPY": "Eq", "IEF": "Bond", "LQD": "Bond", "GLD": "Real"})
    assert html.lstrip().startswith("<!doctype html>")
    assert "http://" not in html and "https://" not in html and "src=" not in html   # fully self-contained
    for section in ("Equity curve", "Drawdown", "Rolling", "Monthly returns", "Risk", "attribution"):
        assert section in html
    assert res.name in html


def test_leaderboard_ranks_and_shows_the_gauntlet():
    prices = _panel()
    syms = list(prices.columns)
    out = eng.compare([sl.EqualWeight(syms), sl.RiskParity(syms), sl.TimeSeriesMomentum(syms)], prices)
    html = rp.leaderboard_html(out["results"], out["gauntlet"])
    assert html.lstrip().startswith("<!doctype html>") and "Gauntlet" in html
    for r in out["results"]:
        assert r.name in html
    assert out["gauntlet"]["best"] in html
