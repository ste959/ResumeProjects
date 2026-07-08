"""Tests for the portfolio risk math — vol-targeting and correlation-aware portfolio vol (netting)."""

from __future__ import annotations

import numpy as np

from service import risk


def test_ann_vol_scales_with_sqrt_ppy():
    r = [0.01, -0.01] * 50
    v1 = risk.ann_vol(r, ppy=1)
    v252 = risk.ann_vol(r, ppy=252)
    assert abs(v252 - v1 * np.sqrt(252)) < 1e-9


def test_vol_target_sizes_inverse_to_vol_and_clamps():
    lo, hi = 300.0, 3000.0
    n_low_vol = risk.vol_target_notional(1000.0, 0.5, lo, hi)   # 2000
    n_high_vol = risk.vol_target_notional(1000.0, 1.0, lo, hi)  # 1000
    assert n_low_vol > n_high_vol                              # calmer asset → bigger notional
    assert abs(n_high_vol - 1000.0) < 1e-6
    assert risk.vol_target_notional(1000.0, 0.001, lo, hi) == hi   # tiny vol → clamp high
    assert risk.vol_target_notional(1000.0, 100.0, lo, hi) == lo   # huge vol → clamp low
    assert risk.vol_target_notional(1000.0, 0.0, lo, hi) == lo     # unknown vol → floor


def test_portfolio_vol_captures_correlation_netting():
    syms = ["A", "B"]
    sd = 0.02
    corr = np.array([[sd ** 2, sd ** 2], [sd ** 2, sd ** 2]])   # ρ = 1
    ind = np.array([[sd ** 2, 0.0], [0.0, sd ** 2]])            # ρ = 0

    long_long_corr = risk.portfolio_vol({"A": 1000, "B": 1000}, syms, corr)
    long_long_ind = risk.portfolio_vol({"A": 1000, "B": 1000}, syms, ind)
    long_short_corr = risk.portfolio_vol({"A": 1000, "B": -1000}, syms, corr)

    assert abs(long_long_corr - 2 * 1000 * sd) < 1e-6          # correlated longs: risks add (~gross)
    assert long_long_ind < long_long_corr                     # diversification lowers it
    assert long_short_corr < 1e-6                             # correlated long/short nets to ~0


def test_cov_annualized_shape_and_scale():
    rng = np.random.default_rng(0)
    rets = {"A": list(rng.standard_normal(200) * 0.01), "B": list(rng.standard_normal(200) * 0.01)}
    cov = risk.cov_annualized(rets, ["A", "B"], ppy=8760)
    assert cov.shape == (2, 2)
    assert cov[0, 0] > 0 and cov[1, 1] > 0                     # positive variances
    assert abs(cov[0, 1] - cov[1, 0]) < 1e-12                  # symmetric
