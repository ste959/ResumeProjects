"""Tests for tax-aware rebalancing — the lot mechanics that create the after-tax edge: HIFO realizes
smaller gains than FIFO, the long-term holding period is classified correctly, wash sales disallow
harvested losses, and the method comparison shows HIFO is never worse than naive FIFO."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import taxaware as tx


def _ts(s):
    return pd.Timestamp(s)


def test_hifo_realizes_smaller_gain_than_fifo():
    def lots():
        return [tx.Lot(_ts("2021-01-01"), 10, 100.0), tx.Lot(_ts("2021-02-01"), 10, 110.0)]
    fifo = tx._sell(lots(), 10, 120.0, _ts("2021-06-01"), "A", "fifo")
    hifo = tx._sell(lots(), 10, 120.0, _ts("2021-06-01"), "A", "hifo")
    assert sum(e.gain for e in fifo) == 200.0        # sells the $100 lot → 20/sh
    assert sum(e.gain for e in hifo) == 100.0        # sells the $110 lot → 10/sh (smaller gain)
    assert sum(e.gain for e in hifo) < sum(e.gain for e in fifo)


def test_long_term_classification():
    long = tx._sell([tx.Lot(_ts("2020-01-01"), 5, 100.0)], 5, 130.0, _ts("2021-06-01"), "A", "fifo")
    short = tx._sell([tx.Lot(_ts("2021-05-01"), 5, 100.0)], 5, 130.0, _ts("2021-06-01"), "A", "fifo")
    assert long[0].long_term and long[0].holding_days >= tx.LONG_TERM_DAYS
    assert not short[0].long_term


def test_simulate_realizes_gain_on_exit():
    idx = pd.date_range("2021-01-01", periods=2, freq="D")
    prices = pd.DataFrame({"A": [100.0, 120.0]}, index=idx)
    weights = pd.DataFrame({"A": [1.0, 0.0]}, index=idx)          # in, then fully out
    res = tx.simulate(weights, prices, capital=100_000.0, method="fifo")
    total = sum(e.gain for e in res.events)
    assert abs(total - 20_000.0) < 1.0                            # +20% on $100k


def test_wash_sale_disallows_repurchased_loss():
    idx = pd.to_datetime(["2021-01-01", "2021-01-10", "2021-01-15"])
    prices = pd.DataFrame({"A": [100.0, 90.0, 90.0]}, index=idx)
    weights = pd.DataFrame({"A": [1.0, 0.0, 1.0]}, index=idx)     # buy, sell at loss, rebuy in 5 days
    res = tx.flag_wash_sales(tx.simulate(weights, prices, capital=100_000.0, method="fifo"))
    loss_events = [e for e in res.events if e.gain < 0]
    assert loss_events and all(e.disallowed for e in loss_events)
    summ = tx.tax_summary(res)
    assert summ["wash_sale_disallowed"] > 0


def test_no_wash_sale_when_not_repurchased():
    idx = pd.to_datetime(["2021-01-01", "2021-01-10"])
    prices = pd.DataFrame({"A": [100.0, 90.0]}, index=idx)
    weights = pd.DataFrame({"A": [1.0, 0.0]}, index=idx)          # sold at a loss, never rebought
    res = tx.flag_wash_sales(tx.simulate(weights, prices, capital=100_000.0, method="fifo"))
    assert not any(e.disallowed for e in res.events)


def test_compare_methods_hifo_not_worse_than_fifo():
    # Build two A-lots at different basis, then trim — HIFO should defer more gain (lower tax now,
    # higher unrealized gain carried) than FIFO on the identical trade path.
    idx = pd.date_range("2021-01-01", periods=3, freq="30D")
    prices = pd.DataFrame({"A": [100.0, 110.0, 120.0]}, index=idx)
    weights = pd.DataFrame({"A": [0.5, 1.0, 0.5]}, index=idx)
    table = tx.compare_methods(weights, prices, capital=1_000_000.0)
    assert table.loc["hifo", "tax"] <= table.loc["fifo", "tax"] + 1e-6
    assert table.loc["hifo", "deferred_unrealized_gain"] >= table.loc["fifo", "deferred_unrealized_gain"] - 1e-6
    assert table.loc["fifo", "tax_vs_fifo"] == 0.0
