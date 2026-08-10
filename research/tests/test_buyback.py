"""Tests for the buyback-blackout module — blackout windows, point-in-time buyback yield, the mechanism
test, and the dollar-neutral strategy. All network-free (facts are constructed, not fetched)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import buyback as bb


def _idx(n=500):
    return pd.date_range("2021-01-01", periods=n, freq="B")


def test_blackout_mask_marks_the_pre_filing_window():
    idx = _idx()
    filing = "2021-05-10"
    mask = bb.blackout_mask(idx, [filing], pre_days=50, gap_days=8)
    f = pd.Timestamp(filing)
    assert mask.loc[mask.index[(mask.index >= f - pd.Timedelta("40D")) & (mask.index <= f - pd.Timedelta("10D"))]].all()
    assert not mask.loc[mask.index[mask.index > f]].any()      # not in blackout after the filing (earnings out)
    assert not mask.loc[mask.index[mask.index < f - pd.Timedelta("60D")]].any()


def test_pit_ffill_has_no_lookahead():
    idx = _idx()
    pts = [{"filed": "2021-03-15", "val": 10.0}, {"filed": "2021-09-15", "val": 20.0}]
    s = bb._pit_ffill(pts, idx)
    assert np.isnan(s.loc[:"2021-03-14"]).all()                # nothing known before the first filing
    assert (s.loc["2021-03-15":"2021-09-14"] == 10.0).all()    # first value until the next filing
    assert (s.loc["2021-09-15":] == 20.0).all()


def test_buyback_yield_is_repurchase_over_market_cap():
    idx = _idx()
    price = pd.Series(100.0, index=idx)
    facts = {"repurchases": [{"filed": "2021-02-01", "val": 1e9}],      # $1B/yr repurchased
             "shares": [{"filed": "2021-02-01", "val": 1e8}]}           # 100M shares → $10B mktcap
    y = bb.buyback_yield(facts, price)
    assert abs(y.loc["2021-06-01"] - 0.10) < 1e-9              # 1B / (100 × 100M) = 10%


def _panel_with_blackout_drag():
    # Two stocks; HI has a big buyback program and underperforms in its blackout, LO has none.
    idx = _idx(400)
    rng = np.random.default_rng(0)
    px = pd.DataFrame(100.0, index=idx, columns=["HI", "LO"])
    filings = ["2021-05-10", "2021-08-10", "2021-11-10", "2022-02-10", "2022-05-10"]
    mask = pd.DataFrame({"HI": bb.blackout_mask(idx, filings), "LO": bb.blackout_mask(idx, filings)})
    drift = pd.DataFrame({"HI": np.where(mask["HI"], -0.002, 0.001), "LO": 0.0005}, index=idx)
    rets = drift + rng.normal(0, 0.002, (len(idx), 2))
    px = 100 * (1 + rets).cumprod()
    yld = pd.DataFrame({"HI": 0.08, "LO": 0.0}, index=idx)     # HI big program, LO none
    return px, mask, yld


def test_mechanism_test_finds_the_blackout_drag():
    px, mask, yld = _panel_with_blackout_drag()
    out = bb.mechanism_test(px, mask, yld, n_tiles=2)
    hi = out.iloc[-1]                                          # the highest-buyback-intensity tile (last row)
    assert hi["gap_out_minus_in"] > 0                          # out-of-blackout beats in-blackout


def test_backtest_is_dollar_neutral_and_runs():
    px, mask, yld = _panel_with_blackout_drag()
    out = bb.backtest(px, mask, yld, rebalance=5, cost_bps=5.0)
    assert out["weights"].sum(axis=1).abs().max() < 1e-9      # dollar-neutral
    assert len(out["net"]) > 100 and np.isfinite(out["net"].std())
