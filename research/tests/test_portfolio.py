"""Tests for the portfolio optimizer — the properties that make an allocation study trustworthy:
weights are valid, the walk-forward is genuinely out-of-sample, mean-variance tilts toward the
better signal, and diversification across GOOD uncorrelated signals actually raises the Sharpe."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import portfolio as pf


def _panel(seed=0, n=400, k=4, mu=0.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    return pd.DataFrame(rng.normal(mu, 0.01, (n, k)), index=idx,
                        columns=[f"s{i}" for i in range(k)])


def test_weights_are_nonneg_and_sum_to_one():
    win = _panel()
    for method in ("equal", "inverse_vol", "risk_parity", "max_sharpe"):
        w = pf.optimize_weights(win, method)
        assert abs(w.sum() - 1.0) < 1e-9, method
        assert (w >= -1e-12).all(), method


def test_walk_forward_is_out_of_sample():
    # The combined series must start only AFTER the first lookback window — no weight is ever
    # applied to the same block it was estimated on.
    R = _panel(n=300)
    combined, log = pf.walk_forward_allocate(R, method="risk_parity", lookback=126, rebalance=21)
    assert combined.index.min() >= R.index[126]
    assert len(log) >= 1


def test_max_sharpe_tilts_to_the_better_signal():
    # Two signals, identical vol; one has a clearly higher mean. Shrunk mean-variance must give
    # the winner more weight than the loser.
    rng = np.random.default_rng(3)
    idx = pd.date_range("2015-01-01", periods=500, freq="B")
    good = rng.normal(0.0008, 0.01, 500)
    bad = rng.normal(-0.0003, 0.01, 500)
    win = pd.DataFrame({"good": good, "bad": bad}, index=idx)
    w = pf.optimize_weights(win, "max_sharpe")
    assert w[0] > w[1]


def test_diversification_raises_sharpe_on_good_uncorrelated_signals():
    # Four uncorrelated signals, each ~Sharpe 0.7. Allocating across them should beat the
    # average single signal by roughly sqrt(N) — this is the whole point of the optimizer.
    daily_mu = 0.7 / np.sqrt(pf.TRADING_DAYS) * 0.01
    R = _panel(seed=7, n=2000, k=4, mu=daily_mu)
    combined, _ = pf.walk_forward_allocate(R, method="risk_parity", lookback=126, rebalance=21)
    avg_single = np.mean([pf.sharpe(R[c]) for c in R.columns])
    assert pf.sharpe(combined) > 1.4 * avg_single


def test_vol_target_scales_to_requested_vol():
    r = _panel(n=1000, k=1)["s0"]
    scaled = pf.vol_target(r, target_annual_vol=0.10)
    realized = scaled.std(ddof=0) * np.sqrt(pf.TRADING_DAYS)
    assert abs(realized - 0.10) < 1e-9


def test_kelly_is_positive_for_positive_edge_and_zero_for_flat():
    edge = _panel(n=2000, k=1, mu=0.0005)["s0"]
    assert pf.kelly_fraction(edge) > 0
    assert pf.kelly_fraction(pd.Series([0.0, 0.0, 0.0])) == 0.0
