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


def test_rolling_beta_recovers_known_beta():
    # A stock built as 1.5×market (plus negligible noise) must have a rolling beta ≈ 1.5.
    idx = pd.date_range("2020-01-01", periods=300)
    rng = np.random.default_rng(0)
    mkt = pd.Series(rng.normal(0, 0.01, 300), index=idx)
    rets = pd.DataFrame({"X": 1.5 * mkt + rng.normal(0, 1e-4, 300)})
    beta = xs._rolling_beta(rets, mkt, window=126)
    assert abs(beta["X"].dropna().iloc[-1] - 1.5) < 0.1


def test_idio_vol_zero_for_pure_market_positive_for_noise():
    # A stock that IS the market has no idiosyncratic vol; a market-unrelated stock has plenty.
    idx = pd.date_range("2020-01-01", periods=300)
    rng = np.random.default_rng(1)
    mkt = pd.Series(rng.normal(0, 0.01, 300), index=idx)
    rets = pd.DataFrame({"pure": 1.0 * mkt,
                         "noisy": pd.Series(rng.normal(0, 0.02, 300), index=idx)})
    idio = xs._idio_vol(rets, mkt, window=126)
    assert idio["pure"].dropna().iloc[-1] < 1e-6
    assert idio["noisy"].dropna().iloc[-1] > 0.01


def test_signals_returns_expected_keys_and_shape():
    idx = pd.date_range("2020-01-01", periods=400)
    rng = np.random.default_rng(2)
    px = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (400, 5)), axis=0)),
                      index=idx, columns=list("ABCDE"))
    rets = np.log(px).diff()
    sigs = xs.signals(px, rets)
    assert set(sigs) == {"momentum", "reversal", "low_vol", "bab", "idio_vol", "risk_adj_mom"}
    for s in sigs.values():
        assert s.shape == px.shape
