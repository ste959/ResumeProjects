"""Tests for the long-history data layer — the pure yfinance panel extraction and risk-free conversion
(network-free; a synthetic yfinance-shaped frame is constructed)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import longdata as ld


def _yf_frame(symbols, rf_symbol, n=50):
    idx = pd.date_range("2010-01-04", periods=n, freq="B")
    cols = pd.MultiIndex.from_product([["Close", "High", "Low", "Volume"], symbols + [rf_symbol]],
                                      names=["Price", "Ticker"])
    rng = np.random.default_rng(0)
    data = rng.uniform(50, 200, (n, len(cols)))
    df = pd.DataFrame(data, index=idx, columns=cols)
    df[("Close", rf_symbol)] = 4.5                              # 4.5% T-bill yield level
    return df


def test_extract_panels_shapes_and_symbols():
    syms = ["SPY", "IEF", "GLD"]
    panels, rf = ld._extract_panels(_yf_frame(syms, "^IRX"), syms, "^IRX")
    assert set(panels) == {"close", "high", "low", "volume"}
    for f, p in panels.items():
        assert list(p.columns) == syms                          # rf symbol excluded from the panels
        assert p.shape[0] == 50


def test_risk_free_is_annual_percent_to_daily():
    syms = ["SPY", "IEF"]
    _, rf = ld._extract_panels(_yf_frame(syms, "^IRX"), syms, "^IRX")
    assert abs(rf.iloc[0] - 0.045 / 252.0) < 1e-12              # 4.5% / 100 / 252 → daily
