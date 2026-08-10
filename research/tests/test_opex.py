"""Tests for the OPEX module — the expiration calendar, phase classification, the timing strategy, and
the Black–Scholes gamma methodology."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import opex


def _idx(n=500):
    return pd.date_range("2021-01-01", periods=n, freq="B")


def test_monthly_expiries_are_third_fridays():
    exp = opex.monthly_expiries(_idx())
    assert (exp.weekday == 4).all()                                # all Fridays
    assert ((exp.day >= 15) & (exp.day <= 21)).all()               # 3rd Friday falls on the 15th–21st


def test_phase_classification_marks_expiry_and_the_week_after():
    idx = _idx()
    phase = opex.opex_phase(idx)
    exp = opex.monthly_expiries(idx)
    e = exp[exp.isin(idx)][0]
    pos = idx.get_loc(e)
    assert phase.iloc[pos] == "opex_week"                          # expiry day itself
    assert phase.iloc[pos + 1] == "post_opex"                      # the session after
    assert set(phase.unique()) <= {"opex_week", "post_opex", "rest"}


def test_phase_return_study_runs():
    idx = _idx()
    prices = pd.Series(100 * np.cumprod(1 + np.random.default_rng(0).normal(0.0003, 0.01, len(idx))), index=idx)
    study = opex.phase_return_study(prices)
    assert set(study.index) <= {"opex_week", "post_opex", "rest"} and "t_stat" in study.columns


def test_opex_timing_flattens_in_the_weak_phase():
    idx = _idx()
    prices = pd.DataFrame({"SPY": 100 * np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, len(idx)))}, index=idx)
    strat = opex.OpexTiming("SPY")
    strat.prepare(prices)
    phase = opex.opex_phase(idx)
    post = np.where(phase.to_numpy() == "post_opex")[0]
    rest = np.where(phase.to_numpy() == "rest")[0]
    assert strat.target_weights(prices, post[5] + 1)[0] == 0.0     # flat the day after a post_opex classification
    assert strat.target_weights(prices, rest[20] + 1)[0] == 1.0    # long in the rest phase


def test_bs_gamma_peaks_near_the_money():
    atm = opex.bs_gamma(100, 100, 0.1, 0.2)
    otm = opex.bs_gamma(100, 130, 0.1, 0.2)
    assert atm > otm > 0                                           # gamma is largest ATM, positive, decays OTM
    assert opex.bs_gamma(100, 100, 0.0, 0.2) == 0.0                # no time → no gamma


def test_gamma_by_strike_runs_on_a_small_chain():
    chain = pd.DataFrame({
        "strike": [90, 100, 110, 100], "iv": [0.25, 0.2, 0.22, 0.2],
        "expiry": ["2030-01-18"] * 4, "right": ["call", "call", "call", "put"], "volume": [100, 500, 200, 400]})
    out = opex.gamma_by_strike(chain, spot=100.0)
    assert "gamma_exposure" in out.columns and len(out) == 3       # aggregated to 3 unique strikes
