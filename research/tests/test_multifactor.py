"""Tests for the multi-factor book — the price-factor signals, the cross-sectional z-score, and that the
composite book runs through the inherited deployment stack (dollar-neutral)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import multifactor as mf


def _panel(n=500, k=20, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-04", periods=n, freq="B")
    cols = [f"S{i}" for i in range(k)] + ["SPY"]
    rets = rng.normal(0.0003, 0.012, (n, k + 1))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=cols)


def test_momentum_skips_the_last_month():
    px = _panel(400, 3)
    m = mf.momentum(px, lookback=252, skip=21)
    assert abs(m["S0"].iloc[300] - (px["S0"].shift(21).iloc[300] / px["S0"].shift(252).iloc[300] - 1)) < 1e-12


def test_low_vol_and_reversal_signs():
    px = _panel(300, 3)
    assert (mf.low_volatility(px).dropna() <= 0).all().all()            # −vol is non-positive
    # reversal is the negative of the last-month return
    assert abs(mf.short_reversal(px)["S0"].iloc[100] - (-(px["S0"].iloc[100] / px["S0"].iloc[79] - 1))) < 1e-12


def test_xs_z_is_standardized_each_date():
    px = _panel(400, 10)                                                # enough history for a 252d momentum
    z = mf._xs_z(mf.momentum(px)).dropna()
    assert z.mean(axis=1).abs().max() < 1e-9                            # cross-sectional mean ≈ 0
    assert (z.std(axis=1) - 1).abs().max() < 1e-6                       # unit cross-sectional std


def test_multifactor_book_runs_and_is_dollar_neutral():
    px = _panel(600)
    stocks = [c for c in px.columns if c != "SPY"]
    r = eng.run(mf.MultiFactorBook(stocks, factors=("mom", "lowvol"), enh=frozenset({"clean", "neutralize"})),
                px, eng.BacktestConfig(rebalance=21, cost_bps=0.0))
    assert np.isfinite(r.stats["sharpe"])
    assert r.weights[stocks].sum(axis=1).abs().max() < 1e-6            # market-neutral (dollar-neutral) book


def test_name_reflects_the_factors():
    assert mf.MultiFactorBook(["A", "B"], factors=("mom", "lowvol", "rev")).name == "mom+lowvol+rev"
