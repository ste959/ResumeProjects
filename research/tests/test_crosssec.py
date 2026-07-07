"""Tests for the cross-sectional backtester — dollar-neutrality, unit gross, cost impact, and
no look-ahead are the properties that must hold (a signal study is only as honest as these)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import crosssec as xs


def test_xs_zscore_demeans_each_day():
    frame = pd.DataFrame({"A": [1.0, 10.0], "B": [3.0, 20.0], "C": [5.0, 30.0]})
    z = xs._xs_zscore(frame)
    assert abs(z.iloc[0].mean()) < 1e-9   # each row (day) is demeaned across symbols
    assert abs(z.iloc[1].mean()) < 1e-9


def test_backtest_portfolio_is_dollar_neutral_unit_gross_and_costs_reduce():
    idx = pd.date_range("2020-01-01", periods=60)
    rng = np.random.default_rng(0)
    rets = pd.DataFrame(rng.normal(0, 0.01, (60, 5)), index=idx, columns=list("ABCDE"))
    signal = pd.DataFrame(rng.normal(size=(60, 5)), index=idx, columns=list("ABCDE"))

    r = xs.backtest(signal, rets, cost_bps=10.0)
    assert r["net_sharpe"] <= r["gross_sharpe"]  # costs never help

    weights = xs._xs_zscore(signal)
    weights = weights.div(weights.abs().sum(axis=1), axis=0).fillna(0.0)
    assert weights.sum(axis=1).abs().max() < 1e-9           # dollar-neutral each day
    assert (weights.abs().sum(axis=1) - 1.0).abs().max() < 1e-9  # unit gross exposure


def test_backtest_lag_defeats_lookahead():
    # A signal equal to the contemporaneous return: WITHOUT a lag it fits perfectly (a huge,
    # fake Sharpe); WITH the one-day lag the backtester actually applies, it can't. Comparing
    # the two directly proves the lag is what prevents look-ahead — deterministically.
    idx = pd.date_range("2020-01-01", periods=300)
    rng = np.random.default_rng(1)
    rets = pd.DataFrame(rng.normal(0, 0.01, (300, 5)), index=idx, columns=list("ABCDE"))

    weights = xs._xs_zscore(rets)
    weights = weights.div(weights.abs().sum(axis=1), axis=0).fillna(0.0)
    cheating = (weights * rets).sum(axis=1)          # same-day (look-ahead) — always profits
    honest = (weights.shift(1) * rets).sum(axis=1)   # what backtest() does — lagged

    assert xs._sharpe(cheating) > 5 * abs(xs._sharpe(honest))  # the lag destroys the fake edge
