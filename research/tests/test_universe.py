"""Tests for the point-in-time universe — membership as-of a date, the survivorship audit, and the
engine's PIT masking + delisting-loss realization (the survivorship-bias fix)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import strategies_lib as sl
from mds import universe as un


def _panel_with_entry_and_exit():
    idx = pd.date_range("2021-01-01", periods=200, freq="B")
    df = pd.DataFrame(100.0, index=idx, columns=["OLD", "IPO", "DEAD"])
    df.iloc[:80, df.columns.get_loc("IPO")] = np.nan     # lists on day 80
    df.iloc[130:, df.columns.get_loc("DEAD")] = np.nan   # delists on day 130
    return df, idx


def test_first_and_last_dates_track_listing_and_delisting():
    df, idx = _panel_with_entry_and_exit()
    u = un.PointInTimeUniverse(df)
    assert u.first_dates()["IPO"] == idx[80]
    assert u.last_dates()["DEAD"] == idx[129]
    assert u.first_dates()["OLD"] == idx[0] and u.last_dates()["OLD"] == idx[-1]


def test_membership_mask_is_true_only_while_listed():
    df, idx = _panel_with_entry_and_exit()
    mask = un.PointInTimeUniverse(df).membership_mask()
    assert not mask["IPO"].iloc[79] and mask["IPO"].iloc[80]      # off before listing, on after
    assert mask["DEAD"].iloc[129] and not mask["DEAD"].iloc[130]  # on until delisting, off after


def test_survivorship_audit_counts_entries_and_exits():
    df, _ = _panel_with_entry_and_exit()
    a = un.survivorship_audit(df)
    assert a["n_entries"] == 1 and a["entries"] == ["IPO"]
    assert a["n_exits"] == 1 and a["exits"] == ["DEAD"]
    assert a["n_full_history"] == 1                                # only OLD spans the whole window


def test_engine_realizes_the_delisting_loss():
    # Flat prices everywhere → the ONLY P&L is the delisting haircut when the held DEAD name exits.
    idx = pd.date_range("2021-01-01", periods=200, freq="B")
    df = pd.DataFrame(100.0, index=idx, columns=["A", "B", "DEAD"])
    df.iloc[130:, df.columns.get_loc("DEAD")] = np.nan
    u = un.PointInTimeUniverse(df, delisting_return=-0.5)
    res = eng.run(sl.EqualWeight(["A", "B", "DEAD"]), df,
                  eng.BacktestConfig(rebalance=21, cost_bps=0.0), universe=u)
    # Held 1/3 in DEAD; at the first rebalance after delisting it takes −50% → a ≈ −1/6 hit, then 0.
    assert res.net.min() < -0.10
    assert (res.weights["DEAD"].loc[idx[150]:] == 0).all()   # zero after the delisting is processed


def test_pit_universe_does_not_trade_a_name_before_it_lists():
    df, idx = _panel_with_entry_and_exit()
    u = un.PointInTimeUniverse(df)
    res = eng.run(sl.EqualWeight(["OLD", "IPO", "DEAD"]), df,
                  eng.BacktestConfig(rebalance=5, cost_bps=0.0), universe=u)
    # Before the IPO lists (day 80), the engine must hold zero of it (no look-ahead into a not-yet-listed name).
    early = res.weights["IPO"].loc[:idx[70]]
    assert (early == 0).all()
