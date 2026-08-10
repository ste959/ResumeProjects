"""Tests for cross-sectional stat-arb — statistical factors, residual orthogonality, the OU s-score sign,
and the strategy's factor-/dollar-neutral construction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import xstatarb as xs


def _factor_panel(n=400, n_stocks=30, seed=0):
    """Returns = a common market factor + a mean-reverting idiosyncratic residual (so reversal has bite)."""
    rng = np.random.default_rng(seed)
    mkt = rng.normal(0, 0.01, n)
    betas = rng.uniform(0.5, 1.5, n_stocks)
    resid = np.zeros((n, n_stocks))
    for j in range(n_stocks):                                   # AR(1) mean-reverting idiosyncratic
        for i in range(1, n):
            resid[i, j] = 0.6 * resid[i - 1, j] + rng.normal(0, 0.01)
    R = np.outer(mkt, betas) + resid
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    cols = [f"S{j}" for j in range(n_stocks)]
    return pd.DataFrame(100 * np.cumprod(1 + R, axis=0), index=idx, columns=cols)


def test_eigen_factor_returns_shape():
    R = _factor_panel().pct_change().dropna().to_numpy()
    F = xs.eigen_factor_returns(R, k=3)
    assert F.shape == (len(R), 3)


def test_residuals_are_orthogonal_to_factors():
    R = _factor_panel().pct_change().dropna().to_numpy()
    F = xs.eigen_factor_returns(R, k=3)
    e = xs.residualize(R, F)
    # OLS residuals are orthogonal to the regressors (Fᵀe ≈ 0) — this is the factor-neutralization.
    assert np.abs(F.T @ e).max() < 1e-8


def test_s_score_sign_flags_a_stretched_residual():
    # A residual whose cumulative process ends far ABOVE its mean → positive s-score → short signal.
    n = 120
    resid = np.zeros((n, 1))
    rng = np.random.default_rng(1)
    for i in range(1, n):
        resid[i, 0] = 0.5 * resid[i - 1, 0] + rng.normal(0, 0.01)
    resid[-5:, 0] += 0.05                                        # push the recent residual up hard
    s = xs.s_scores(resid, kappa_min=0.0)
    assert s[0] > 0                                              # stretched high → s>0 → alpha=−s<0 (short)


def test_weights_are_dollar_neutral_and_gross_scaled():
    prices = _factor_panel()
    strat = xs.CrossSectionalStatArb(list(prices.columns), window=60, k=3, gross=1.0)
    strat.prepare(prices)
    w = strat.target_weights(prices, 120)
    assert abs(w.sum()) < 1e-9                                   # dollar-neutral (longs fund shorts)
    assert abs(np.abs(w).sum() - 1.0) < 1e-9                     # gross scaled to 1


def test_strategy_runs_through_the_engine():
    prices = _factor_panel(n=500)
    res = eng.run(xs.CrossSectionalStatArb(list(prices.columns), window=60, k=3),
                  prices, eng.BacktestConfig(rebalance=1, cost_bps=0.0))
    assert np.isfinite(res.stats["sharpe"]) and res.stats["n_days"] > 100
