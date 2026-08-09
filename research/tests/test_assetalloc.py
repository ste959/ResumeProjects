"""Tests for the multi-asset allocation module — the allocators' defining properties and a
walk-forward backtest sanity check."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import assetalloc as aa


def _cov(vols, corr):
    d = np.diag(vols)
    return d @ corr @ d


def test_risk_parity_equalizes_risk_contributions():
    # Correlated assets with different vols → equal-risk-contribution weights should give each asset
    # the SAME share of portfolio variance (the defining property of true risk parity).
    cov = _cov([0.10, 0.20, 0.15], np.array([[1.0, 0.5, 0.2], [0.5, 1.0, 0.3], [0.2, 0.3, 1.0]]))
    w = aa.risk_parity(cov)
    rc = aa.risk_contributions(w, cov)
    assert abs(w.sum() - 1.0) < 1e-9 and (w >= 0).all()
    assert (rc.max() - rc.min()) / rc.mean() < 0.02        # risk contributions ~equal


def test_risk_parity_downweights_a_redundant_pair():
    # Equal vols → inverse-vol is just equal-weight (1/3 each). But assets 0 and 1 are highly correlated
    # (redundant), so true risk parity must DOWNWEIGHT that pair and lift the independent asset 2 —
    # exactly the correlation-awareness inverse-vol misses.
    cov = _cov([0.15, 0.15, 0.15], np.array([[1.0, 0.9, 0.0], [0.9, 1.0, 0.0], [0.0, 0.0, 1.0]]))
    w = aa.risk_parity(cov)
    assert np.abs(w - aa.inverse_vol(cov)).max() > 0.02
    assert w[2] > w[0] and w[2] > w[1]                     # independent asset gets the most weight


def test_inverse_vol_is_proportional_to_one_over_sigma():
    cov = _cov([0.10, 0.20, 0.40], np.eye(3))
    w = aa.inverse_vol(cov)
    # ratios of weights equal ratios of 1/sigma
    assert abs(w[0] / w[1] - (1 / 0.10) / (1 / 0.20)) < 1e-9


def test_min_variance_overweights_the_calm_asset():
    cov = _cov([0.05, 0.30, 0.30], np.array([[1.0, 0.2, 0.2], [0.2, 1.0, 0.2], [0.2, 0.2, 1.0]]))
    w = aa.min_variance(cov)
    assert abs(w.sum() - 1.0) < 1e-6 and (w >= -1e-9).all()
    assert w[0] == max(w)                                   # the low-vol asset gets the largest weight


def test_momentum_tilt_favors_higher_momentum():
    base = np.array([0.25, 0.25, 0.25, 0.25])
    mom = np.array([-0.1, 0.0, 0.1, 0.2])                   # asset 3 strongest
    w = aa.momentum_tilt(base, mom, strength=0.5)
    assert abs(w.sum() - 1.0) < 1e-9
    assert w[3] > w[0]                                      # winner overweighted vs. loser


def _synthetic_prices(seed=0, n=700):
    rng = np.random.default_rng(seed)
    cols = list(aa.UNIVERSE)                                # includes SPY + IEF for the 60/40 benchmark
    k = len(cols)
    daily = rng.normal(0.0003, 0.01, size=(n, k))
    prices = 100 * np.cumprod(1 + daily, axis=0)
    idx = pd.bdate_range("2021-01-01", periods=n)
    return pd.DataFrame(prices, index=idx, columns=cols)


def test_backtest_runs_and_is_diversified():
    prices = _synthetic_prices()
    r = aa.backtest(prices, method="risk_parity", lookback=252, rebalance=21)
    assert r["n_days"] > 100
    assert np.isfinite(r["sharpe"]) and np.isfinite(r["hac_t"])
    # a risk-parity blend must be less volatile than the most volatile single asset
    single_vols = prices.pct_change().dropna().std().to_numpy() * np.sqrt(aa.TRADING_DAYS)
    assert r["ann_vol"] < single_vols.max()


def test_study_covers_all_methods_plus_benchmark():
    s = aa.study(_synthetic_prices(), cost_bps=10.0)
    names = {row["method"] for row in s["results"]}
    assert {"risk_parity", "min_variance", "max_sharpe", "risk_parity_taa", "60/40"} <= names
    assert all("sharpe" in row and "max_drawdown" in row for row in s["results"])


def test_study_runs_the_selection_aware_gauntlet():
    g = aa.study(_synthetic_prices(), cost_bps=10.0)["gauntlet"]
    # the study must report multiple-testing / overfitting / power stats, not just raw Sharpes
    for k in ("best", "bonferroni_t", "deflated_sharpe", "pbo", "min_detectable_sharpe", "n_strategies"):
        assert k in g
    assert g["n_strategies"] == 7 and 0.0 <= g["pbo"] <= 1.0


def test_excess_return_lowers_sharpe():
    # A positive constant risk-free rate must reduce a strategy's Sharpe (it's a risk *premium*).
    prices = _synthetic_prices()
    raw = aa.backtest(prices, "risk_parity")["sharpe"]
    rf = pd.Series(0.0002, index=prices.index)               # ~5%/yr cash
    net_of_cash = aa.backtest(prices, "risk_parity", rf=rf)["sharpe"]
    assert net_of_cash < raw


def test_stats_report_tail_metrics():
    r = aa.backtest(_synthetic_prices(), "risk_parity")
    for k in ("sortino", "calmar", "cvar_5", "skew"):
        assert k in r


def test_regime_study_slices_by_period():
    prices = _synthetic_prices(n=800)
    regimes = [("first", "2021-01-01", "2022-06-30"), ("second", "2022-07-01", "2024-12-31")]
    reg = aa.regime_study(prices, regimes)
    assert [r["regime"] for r in reg] == ["first", "second"]
    assert "risk_parity" in reg[0]["sharpe"] and "60/40" in reg[0]["sharpe"]


def test_sensitivity_sweep_runs():
    grid = aa.sensitivity(_synthetic_prices(), lookbacks=(252,), rebalances=(21,), costs=(10.0,))
    assert len(grid) == 1
    assert {"lookback", "rebalance", "cost_bps", "winner", "clears_bar"} <= set(grid[0])


def test_optimizers_dont_blow_up_on_ill_conditioned_cov():
    # Two near-duplicate assets → a near-singular covariance. Naive MVO error-maximizes into one name;
    # the shrinkage + convergence fallback must still return valid long-only weights (sum 1, no NaN).
    rng = np.random.default_rng(1)
    base = rng.standard_normal((300, 1)) * 0.01
    R = np.hstack([base, base + rng.standard_normal((300, 1)) * 1e-6, rng.standard_normal((300, 3)) * 0.01])
    df = pd.DataFrame(R)
    shrunk = aa._shrink_cov(df)
    for w in (aa.min_variance(shrunk), aa.max_sharpe(df.mean().to_numpy() * aa.TRADING_DAYS, shrunk)):
        assert np.all(np.isfinite(w)) and abs(w.sum() - 1.0) < 1e-6 and (w >= -1e-9).all()
