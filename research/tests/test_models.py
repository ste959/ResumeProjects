"""Tests for the model zoo + cost-aware backtest — the financial logic (costs, lag) and the
out-of-sample discipline are what must hold."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mds import lob, models


def test_net_backtest_charges_costs_below_gross():
    fwd = np.array([0.001, -0.001, 0.001, -0.001, 0.001])
    position = np.array([1.0, -1.0, 1.0, -1.0, 1.0])  # flips every step → heavy turnover
    r = models.net_backtest(fwd, position, spread_bps=np.full(5, 2.0), fee_bps=1.0)
    assert r["cost_bps"] > 0
    assert r["net_ret_bps"] < r["gross_ret_bps"]  # costs always eat into gross


def test_net_backtest_lags_position_by_one():
    # A held position earns the NEXT return, not the current one (no look-ahead).
    fwd = np.array([0.0, 0.01, 0.0, 0.0])
    position = np.array([1.0, 0.0, 0.0, 0.0])  # long only at t=0 → earns fwd[1]
    r = models.net_backtest(fwd, position, spread_bps=np.zeros(4), fee_bps=0.0)
    assert r["gross_ret_bps"] == pytest.approx(0.01 * 1e4, abs=1e-6)


def test_walk_forward_predict_is_out_of_sample_and_learns():
    pytest.importorskip("sklearn")
    from sklearn.linear_model import Ridge

    n = 300
    x = np.random.default_rng(0).normal(size=n)
    noise = np.random.default_rng(1).normal(size=n)
    df = pd.DataFrame({
        "imbalance": x, "micro_prem_bps": 0.5 * x, "spread_bps": np.ones(n),
        "depth_imb": x, "trade_flow": np.zeros(n), "ret_1": np.zeros(n), "rvol": np.zeros(n),
        "fwd_ret": 0.001 * x + 0.0002 * noise,  # a learnable linear relationship
    })
    pred = models.walk_forward_predict(df, lob.FEATURES, lambda: Ridge(alpha=1.0), folds=4)

    mask = np.isfinite(pred)
    assert mask.sum() > 0                       # test folds were predicted
    assert not mask[:10].any()                  # the first (pre-training) rows stay unpredicted
    # Out-of-sample predictions track the true relationship.
    assert np.corrcoef(pred[mask], df["fwd_ret"].to_numpy()[mask])[0, 1] > 0.5


def test_net_backtest_horizon_avoids_overbooking_overlapping_returns():
    # With a horizon-H label, consecutive samples overlap. A persistent position summed every
    # step books each move ~H times; accounting on non-overlapping (every-H) samples counts each
    # once. So the horizon-aware gross should be ~1/H of the naive every-step gross, not equal.
    n, h = 120, 6
    fwd = np.full(n, 0.001)          # constant H-step forward return
    position = np.ones(n)            # always long
    spread = np.zeros(n)
    naive = models.net_backtest(fwd, position, spread, fee_bps=0.0, horizon=1)
    aware = models.net_backtest(fwd, position, spread, fee_bps=0.0, horizon=h)
    ratio = aware["gross_ret_bps"] / naive["gross_ret_bps"]
    assert 1.0 / h * 0.8 < ratio < 1.0 / h * 1.3   # ~1/H, i.e. overlap no longer double-counts
