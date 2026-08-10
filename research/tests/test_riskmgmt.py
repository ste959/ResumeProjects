"""Tests for the risk-management analytics — VaR/ES, marginal risk contributions, stress replay, and
limit checks."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import riskmgmt as rm


def _rng():
    return np.random.default_rng(0)


def test_var_grows_with_confidence_and_is_a_positive_loss():
    r = _rng().normal(0, 0.01, 5000)
    v95 = rm.value_at_risk(r, 0.95, "historical")
    v99 = rm.value_at_risk(r, 0.99, "historical")
    assert v99 > v95 > 0                                   # 99% VaR is a bigger loss; both positive


def test_expected_shortfall_is_worse_than_var():
    r = _rng().normal(0, 0.01, 5000)
    assert rm.expected_shortfall(r, 0.95) >= rm.value_at_risk(r, 0.95, "historical")


def test_cornish_fisher_sees_fatter_left_tail_than_gaussian():
    # Negatively-skewed, fat-tailed returns → the fat-tail-aware VaR should exceed the Gaussian one.
    rng = _rng()
    r = rng.normal(0, 0.01, 20000) - rng.standard_gamma(2.0, 20000) * 0.003   # left skew + fat tail
    assert rm.value_at_risk(r, 0.95, "cornish_fisher") > rm.value_at_risk(r, 0.95, "gaussian")


def test_marginal_risk_contributions_sum_to_portfolio_vol():
    cov = np.array([[0.04, 0.01, 0.00], [0.01, 0.09, 0.00], [0.00, 0.00, 0.01]])
    w = np.array([0.5, 0.3, 0.2])
    mctr = rm.marginal_risk_contributions(w, cov)
    assert abs(mctr.sum() - np.sqrt(w @ cov @ w)) < 1e-12   # contributions reconcile to total vol


def test_risk_report_risk_contribution_sums_to_one():
    idx = pd.date_range("2021-01-01", periods=300, freq="B")
    net = pd.Series(_rng().normal(0.0003, 0.008, 300), index=idx)
    cov = np.diag([0.0001, 0.0002, 0.00015])
    w = pd.Series([0.4, 0.4, 0.2], index=["SPY", "IEF", "GLD"])
    rep = rm.risk_report(net, weights=w, cov=cov, sleeves={"SPY": "Eq", "IEF": "Bond", "GLD": "Real"})
    assert abs(sum(rep["risk_contribution"].values()) - 1.0) < 1e-6
    assert rep["ann_vol"] > 0 and rep["var_95_hist"] > 0


def test_stress_test_replays_a_crash_through_the_current_book():
    idx = pd.date_range("2021-01-01", periods=200, freq="B")
    prices = pd.DataFrame(100.0, index=idx, columns=["A", "B"])
    prices.iloc[100:120] = prices.iloc[100:120] * 0.9      # a drawdown window in "B"... apply to both
    prices = pd.DataFrame({"A": np.linspace(100, 110, 200), "B": np.r_[np.linspace(100, 105, 100),
                          np.linspace(105, 80, 100)]}, index=idx)
    w = pd.Series([0.5, 0.5], index=["A", "B"])
    out = rm.stress_test(w, prices, [("crash", str(idx[100].date()), str(idx[-1].date()))])
    assert out[0]["book_return"] < 0 and out[0]["worst_day"] < 0


def test_check_limits_flags_breaches():
    idx = pd.date_range("2021-01-01", periods=50, freq="B")
    weights = pd.DataFrame({"SPY": 0.7, "IEF": -0.6}, index=idx)   # gross 1.3, name 0.7
    net = pd.Series(_rng().normal(0, 0.02, 50), index=idx)
    checks = {c["limit"]: c for c in rm.check_limits(weights, net, rm.RiskLimits(max_name_weight=0.6))}
    assert checks["max_name_weight"]["breached"] is True          # 0.7 > 0.6
    assert checks["max_gross"]["breached"] is False               # 1.3 < 2.5
