"""Tests for mechanical-flow reversal — the forced-flow coefficient, overnight returns, the reversal-beta
mechanism test, and the dollar-neutral overnight backtest."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import mechflow as mf


def test_forced_flow_coef_is_positive_for_every_complex():
    coef = mf.forced_flow_coef()
    assert (coef > 0).all()                                   # k(k-1)>0 for all k∉{0,1} → all same-direction
    assert coef["QQQ"] > coef["SPY"]                          # TQQQ dominates → QQQ complex is larger


def test_overnight_returns_are_close_to_next_open():
    idx = pd.date_range("2021-01-01", periods=5, freq="B")
    close = pd.DataFrame({"A": [100, 101, 102, 103, 104]}, index=idx, dtype=float)
    open_ = pd.DataFrame({"A": [100, 102, 101, 104, 103]}, index=idx, dtype=float)
    on = mf.overnight_returns(open_, close)
    assert abs(on["A"].iloc[0] - (102 / 100 - 1)) < 1e-9      # close_0=100 → open_1=102
    assert np.isnan(on["A"].iloc[-1])                          # no next open for the last day


def test_reversal_betas_detect_overnight_mean_reversion():
    # Construct overnight returns that reverse the day's move → the regression beta must be negative.
    rng = np.random.default_rng(0)
    idx = pd.date_range("2021-01-01", periods=400, freq="B")
    daily = rng.normal(0, 0.01, 400)
    close = pd.DataFrame({"REV": 100 * np.cumprod(1 + daily)}, index=idx)
    overnight = pd.DataFrame({"REV": -0.5 * daily + rng.normal(0, 0.002, 400)}, index=idx)  # reverts the move
    betas = mf.reversal_betas(close, overnight)
    assert betas.loc["REV", "beta"] < 0 and betas.loc["REV", "t_stat"] < 0


def _ohlcv(n=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    syms = ["QQQ", "SOXX", "SPY", "IWM"]
    close = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.0003, 0.012, (n, len(syms))), axis=0),
                         index=idx, columns=syms)
    open_ = close.shift(1) * (1 + rng.normal(0, 0.004, (n, len(syms))))     # next open near prior close
    vol = pd.DataFrame(rng.uniform(1e6, 5e7, (n, len(syms))), index=idx, columns=syms)
    return open_.bfill(), close, vol


def test_backtest_is_dollar_neutral_and_runs():
    open_, close, vol = _ohlcv()
    out = mf.backtest_overnight(open_, close, vol)
    assert out["weights"].sum(axis=1).abs().max() < 1e-9      # dollar-neutral every night
    assert len(out["net"]) > 200 and np.isfinite(out["net"].std())


def test_relative_flow_ranks_semis_above_spy():
    open_, close, vol = _ohlcv()
    # Give SPY far more volume (deeper tape) → its relative forced flow should be the smallest.
    vol["SPY"] *= 50
    rel = mf.relative_flow(close, vol)
    assert rel["SPY"] < rel["SOXX"]                            # SPY too liquid → weakest mechanical intensity
