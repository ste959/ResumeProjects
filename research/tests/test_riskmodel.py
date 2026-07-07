"""Tests for the factor risk model + constrained optimizer — the guarantees that make the book
investable: the constrained MVO respects dollar-neutrality and factor-neutrality analytically, box
caps bind, the turnover budget holds, and the structured covariance is positive-definite."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import riskmodel as rm


def test_ewma_cov_recovers_known_covariance():
    rng = np.random.default_rng(0)
    true = np.array([[1.0, 0.5], [0.5, 2.0]])
    L = np.linalg.cholesky(true)
    X = rng.normal(size=(4000, 2)) @ L.T
    est = rm.ewma_cov(X, halflife=1e6)          # ~flat weights → sample cov
    assert np.max(np.abs(est - true)) < 0.15


def test_optimize_is_dollar_neutral_and_unit_gross():
    rng = np.random.default_rng(1)
    n = 12
    alpha = rng.normal(size=n)
    Sigma = np.eye(n)
    C = np.ones((1, n))                          # dollar-neutral
    w = rm.optimize(alpha, Sigma, C, gross=1.0)
    assert abs(w.sum()) < 1e-9
    assert abs(np.abs(w).sum() - 1.0) < 1e-9
    # with Σ=I and only the dollar-neutral constraint, w ∝ demeaned alpha
    demeaned = alpha - alpha.mean()
    assert abs(np.corrcoef(w, demeaned)[0, 1] - 1.0) < 1e-9


def test_optimize_enforces_factor_neutrality():
    rng = np.random.default_rng(2)
    n = 20
    alpha = rng.normal(size=n)
    Sigma = np.eye(n)
    beta = rng.normal(size=n)                    # a factor exposure to neutralize
    C = np.vstack([np.ones(n), beta])            # dollar- AND beta-neutral
    w = rm.optimize(alpha, Sigma, C, gross=1.0)
    assert abs(w.sum()) < 1e-9
    assert abs(float(beta @ w)) < 1e-8           # net beta exposure ≈ 0


def test_position_cap_binds():
    rng = np.random.default_rng(3)
    n = 10
    alpha = rng.normal(size=n)
    w = rm.optimize(alpha, np.eye(n), np.ones((1, n)), gross=1.0, position_cap=0.15)
    assert np.abs(w).max() <= 0.15 + 1e-6
    assert abs(w.sum()) < 1e-6                    # still dollar-neutral after capping


def test_turnover_budget_caps_trade():
    rng = np.random.default_rng(4)
    n = 15
    alpha = rng.normal(size=n)
    w_prev = np.zeros(n)
    w = rm.optimize(alpha, np.eye(n), np.ones((1, n)), gross=1.0,
                    w_prev=w_prev, max_turnover=0.1)
    assert np.abs(w - w_prev).sum() <= 0.1 + 1e-9


def test_asset_covariance_is_positive_definite():
    rng = np.random.default_rng(5)
    n, k = 30, 4
    B = rng.normal(size=(n, k))
    F = np.cov(rng.normal(size=(200, k)), rowvar=False)
    d = np.abs(rng.normal(size=n)) + 0.1
    Sigma = rm.asset_covariance(B, F, d)
    assert np.all(np.linalg.eigvalsh(Sigma) > 0)


def test_factor_returns_recover_a_planted_factor():
    # Build returns that are exactly beta·f_t + noise; the cross-sectional regression should recover
    # a factor-return series whose mean sign matches the planted factor return.
    rng = np.random.default_rng(6)
    idx = pd.date_range("2021-01-01", periods=80)
    names = [f"N{i}" for i in range(15)]
    beta_vals = rng.normal(size=15)
    beta = pd.DataFrame(np.tile(beta_vals, (80, 1)), index=idx, columns=names)
    f_true = 0.01 + rng.normal(0, 0.002, 80)
    rets = pd.DataFrame((beta_vals[None, :] * f_true[:, None]) + rng.normal(0, 1e-4, (80, 15)),
                        index=idx, columns=names)
    sectors = {n: "X" for n in names}
    fr, ur, info = rm.cross_sectional_factor_returns(rets, beta, sectors, {}, idx)
    assert "beta" in fr.columns
    assert fr["beta"].mean() > 0                 # planted positive factor return recovered
