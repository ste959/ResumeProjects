"""Offline tests for the SEC-EDGAR fundamentals layer. These NEVER touch the network — they feed
tiny synthetic facts to the pure point-in-time helpers. The two properties that matter:

  1. TTM sums exactly four trailing quarters.
  2. The panel is POINT-IN-TIME: a value appears on/after its `filed` date and NEVER before it
     (anchoring on `filed`, not the period `end`, is the whole no-look-ahead guarantee)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import edgar


def test_ttm_sums_four_trailing_quarters():
    assert edgar._ttm([10.0, 20.0, 30.0, 40.0]) == 100.0
    # Only the last four count (older quarters are dropped from the trailing window).
    assert edgar._ttm([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]) == 4 + 5 + 6 + 7
    assert edgar._ttm([1.0, 2.0, 3.0]) is None            # fewer than 4 → undefined


def test_duration_classifies_quarter_vs_annual_vs_instant():
    q = {"start": "2021-01-01", "end": "2021-03-31"}
    a = {"start": "2021-01-01", "end": "2021-12-31"}
    instant = {"end": "2021-03-31"}                        # no start → balance-sheet instant
    assert 80 <= edgar._duration_days(q) <= 100
    assert 350 <= edgar._duration_days(a) <= 380
    assert edgar._duration_days(instant) is None


def test_pit_level_value_appears_only_on_or_after_filed_date():
    # A single balance-sheet fact: Assets=100 for the quarter ending 2021-03-31, but FILED 2021-05-10
    # (the 10-Q lag). It must be NaN on every day before the filing and 100 from the filing onward —
    # anchoring on `end` (03-31) instead of `filed` (05-10) would leak 40 days of look-ahead.
    obs = [{"val": 100.0, "end": "2021-03-31", "filed": "2021-05-10", "form": "10-Q"}]
    idx = pd.to_datetime(["2021-04-01", "2021-05-09", "2021-05-10", "2021-06-01"])
    ser = edgar._pit_align(edgar._level_points(obs), idx)

    assert np.isnan(ser.loc["2021-04-01"])                # before filing: unknown
    assert np.isnan(ser.loc["2021-05-09"])                # still before filing (even past period end)
    assert ser.loc["2021-05-10"] == 100.0                 # knowable on the filing date
    assert ser.loc["2021-06-01"] == 100.0                 # and forward-filled after


def test_pit_flow_ttm_builds_from_four_quarters_and_is_filed_anchored():
    # Four consecutive quarters of 25 each → TTM 100, first knowable when the 4th quarter is FILED
    # (2022-02-15). Before that filing the TTM does not exist yet.
    def q(end, filed, val):
        start = (pd.Timestamp(end) - pd.Timedelta(days=89)).strftime("%Y-%m-%d")
        return {"val": val, "start": start, "end": end, "filed": filed, "form": "10-Q"}

    obs = [
        q("2021-03-31", "2021-05-10", 25.0),
        q("2021-06-30", "2021-08-09", 25.0),
        q("2021-09-30", "2021-11-08", 25.0),
        q("2021-12-31", "2022-02-15", 25.0),
    ]
    idx = pd.to_datetime(["2021-12-31", "2022-02-14", "2022-02-15", "2022-03-01"])
    ser = edgar._pit_align(edgar._flow_ttm_points(obs), idx)

    assert np.isnan(ser.loc["2021-12-31"])                # 4th quarter ended but NOT yet filed
    assert np.isnan(ser.loc["2022-02-14"])                # day before the filing
    assert ser.loc["2022-02-15"] == 100.0                 # TTM knowable exactly on the filing date
    assert ser.loc["2022-03-01"] == 100.0


def test_flow_ttm_derives_q4_from_annual_minus_three_quarters():
    # Only Q1–Q3 3-month values plus the 10-K ANNUAL are reported (the common case — no standalone
    # Q4). The helper must derive Q4 = annual − (Q1+Q2+Q3) so a full TTM still exists, anchored on
    # the 10-K's filing date.
    def per(start, end, filed, val):
        return {"val": val, "start": start, "end": end, "filed": filed, "form": "10-Q"}

    obs = [
        per("2021-01-01", "2021-03-31", "2021-05-10", 20.0),
        per("2021-04-01", "2021-06-30", "2021-08-09", 20.0),
        per("2021-07-01", "2021-09-30", "2021-11-08", 20.0),
        {"val": 100.0, "start": "2021-01-01", "end": "2021-12-31",     # 10-K annual (12 months)
         "filed": "2022-02-20", "form": "10-K"},
    ]
    idx = pd.to_datetime(["2022-02-19", "2022-02-20"])
    ser = edgar._pit_align(edgar._flow_ttm_points(obs), idx)
    # Q4 = 100 − (20+20+20) = 40; TTM = 20+20+20+40 = 100, knowable on the 10-K filing.
    assert np.isnan(ser.loc["2022-02-19"])
    assert ser.loc["2022-02-20"] == 100.0


def test_field_panel_and_signals_are_offline_and_shaped():
    # Drive the panel + factor construction end-to-end with synthetic facts (no network).
    idx = pd.to_datetime(["2021-06-01", "2021-08-15", "2021-12-01"]).tz_localize("UTC")
    px = pd.DataFrame({"AAA": [10.0, 11.0, 12.0], "BBB": [50.0, 55.0, 60.0]}, index=idx)
    facts = {
        "AAA": {
            "eps": [   # four consecutive quarters ending Q2-2021, last one filed 2021-08-01
                {"val": 1.0, "start": "2020-07-01", "end": "2020-09-30", "filed": "2020-11-01"},
                {"val": 1.0, "start": "2020-10-01", "end": "2020-12-31", "filed": "2021-02-01"},
                {"val": 1.0, "start": "2021-01-01", "end": "2021-03-31", "filed": "2021-05-01"},
                {"val": 1.0, "start": "2021-04-01", "end": "2021-06-30", "filed": "2021-08-01"},
            ],
            "assets": [{"val": 200.0, "end": "2021-06-30", "filed": "2021-08-01"}],
            "gross_profit": [], "equity": [], "net_income": [], "ocf": [], "revenues": [],
        },
    }
    panels = edgar.fundamental_panels(px, facts=facts)
    assert set(panels) == set(edgar.TAGS)
    for pnl in panels.values():
        assert pnl.shape == px.shape                       # aligned to price panel
    # BBB has no facts → all-NaN column, excluded from the cross-section that day.
    assert panels["assets"]["BBB"].isna().all()

    sigs = edgar.fundamental_signals(px, facts=facts)
    assert set(sigs) == {"earnings_yield", "gross_profitability", "roe", "accruals", "asset_growth"}
    # Earnings yield = EPS_ttm / price, appearing only after the 4th quarter is filed (2021-08-01).
    assert np.isnan(sigs["earnings_yield"].loc[idx[0], "AAA"])   # 2021-06-01, TTM not yet filed
    assert abs(sigs["earnings_yield"].loc[idx[1], "AAA"] - 4.0 / 11.0) < 1e-9  # 2021-08-15
