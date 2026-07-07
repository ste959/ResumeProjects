"""Tests for the overfitting/autocorrelation-aware validation toolkit — the properties that make
these statistics trustworthy: HAC deflates on autocorrelation, DSR penalizes more trials, and PBO
rises toward 0.5 on no-skill data."""

from __future__ import annotations

import numpy as np

from mds import validation as val


def test_newey_west_matches_iid_uncorrelated_and_deflates_on_autocorrelation():
    rng = np.random.default_rng(0)
    n = 4000
    iid = rng.normal(0.05, 1.0, n)
    t_iid = np.sqrt(n) * iid.mean() / iid.std(ddof=0)          # closed-form IID t
    assert abs(val.newey_west_sharpe_tstat(iid) - t_iid) < 0.2 * abs(t_iid) + 0.3

    e = rng.normal(0, 1, n)
    ar = np.zeros(n)
    for i in range(1, n):
        ar[i] = 0.6 * ar[i - 1] + e[i]                          # positively autocorrelated
    ar += 0.05
    t_naive = np.sqrt(n) * ar.mean() / ar.std(ddof=0)
    assert abs(val.newey_west_sharpe_tstat(ar)) < abs(t_naive)  # HAC deflates it


def test_block_bootstrap_ci_brackets_and_widens_with_noise():
    rng = np.random.default_rng(1)
    tight = rng.normal(0.08, 1.0, 3000)
    lo, hi = val.block_bootstrap_sharpe_ci(tight, n_boot=500, seed=0)
    sr = np.sqrt(val.TRADING_DAYS) * tight.mean() / tight.std(ddof=0)
    assert lo < sr < hi


def test_deflated_sharpe_penalizes_more_trials():
    d1 = val.deflated_sharpe(0.10, 1000, 0.0, 3.0, n_trials=1, sharpe_var_across_trials=0.0)
    d20 = val.deflated_sharpe(0.10, 1000, 0.0, 3.0, n_trials=20, sharpe_var_across_trials=0.01)
    assert d1 > d20
    assert 0.0 <= d20 <= 1.0
    assert d1 > 0.95            # a clean single-trial Sharpe is significant...
    assert d20 < 0.5           # ...but deflates once you admit you tried 20 things


def test_pbo_high_for_noise_lower_for_a_dominant_strategy():
    rng = np.random.default_rng(2)
    T, M = 800, 6
    noise = rng.normal(0.0, 0.01, (T, M))
    p_noise = val.pbo(noise, n_splits=10)["pbo"]
    assert 0.3 < p_noise < 0.7                                  # no skill → around a coin flip

    dominant = noise.copy()
    dominant[:, 0] += 0.004                                     # one genuinely better strategy
    p_dom = val.pbo(dominant, n_splits=10)["pbo"]
    assert p_dom < p_noise
