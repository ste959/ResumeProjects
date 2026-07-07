"""Tests for the options-implied layer — OCC parsing and the skew computation on a synthetic
chain. No network: `compute_signals` is a pure function of a rows DataFrame, so the smile logic is
verified deterministically without hitting Alpaca."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from mds import options as opt


# ── OCC parsing ─────────────────────────────────────────────────────────────────────────────────
def test_parse_occ_aapl():
    f = opt.parse_occ("AAPL260706C00210000")
    assert f["underlying"] == "AAPL"
    assert f["expiry"] == dt.date(2026, 7, 6)
    assert f["right"] == "C"
    assert f["strike"] == 210.0        # last 8 digits / 1000 = 00210000 / 1000


def test_parse_occ_put_and_fractional_strike():
    # A put with a fractional strike, and a multi-char root — decoding from the right must handle both.
    f = opt.parse_occ("GOOGL260918P00187500")
    assert f["underlying"] == "GOOGL"
    assert f["expiry"] == dt.date(2026, 9, 18)
    assert f["right"] == "P"
    assert f["strike"] == 187.5


# ── skew computation on a synthetic chain ───────────────────────────────────────────────────────
def _synthetic_chain(put_iv_bump: float = 0.05):
    """A tiny one-expiry chain with a put-side IV bump (a realistic downside smile). Deltas span
    both wings so 25Δ/50Δ interpolation is well-defined."""
    asof = dt.date(2026, 1, 1)
    expiry = asof + dt.timedelta(days=30)
    rows = []
    # Calls: delta 0.1..0.9, flat base IV.
    for delta, iv in [(0.90, 0.20), (0.75, 0.20), (0.50, 0.20), (0.25, 0.20), (0.10, 0.20)]:
        rows.append({"underlying": "TEST", "occ": "T", "expiry": expiry, "right": "C",
                     "strike": 100, "iv": iv, "delta": delta, "bid": 1, "ask": 1.1,
                     "mid": 1.05, "volume": 100})
    # Puts: delta -0.1..-0.9, base IV + a downside bump on the OTM (low |delta|) wing.
    for delta, iv in [(-0.90, 0.20), (-0.75, 0.20), (-0.50, 0.20),
                      (-0.25, 0.20 + put_iv_bump), (-0.10, 0.20 + put_iv_bump)]:
        rows.append({"underlying": "TEST", "occ": "T", "expiry": expiry, "right": "P",
                     "strike": 100, "iv": iv, "delta": delta, "bid": 1, "ask": 1.1,
                     "mid": 1.05, "volume": 250})
    return pd.DataFrame(rows), asof


def test_positive_skew_when_put_iv_exceeds_call_iv():
    rows, asof = _synthetic_chain(put_iv_bump=0.05)
    sig = opt.compute_signals(rows, asof=asof)
    assert sig["expiry"] is not None
    assert sig["dte"] == 30
    # 25Δ put IV (0.25) > 25Δ call IV (0.20) → positive risk-reversal skew ("fear").
    assert sig["iv_25p"] > sig["iv_25c"]
    assert sig["skew_25d"] > 0
    assert abs(sig["skew_25d"] - 0.05) < 1e-9
    assert abs(sig["atm_iv"] - 0.20) < 1e-9        # 50Δ IV flat on both sides
    # pcr from daily volume: 5 puts * 250 vs 5 calls * 100.
    assert abs(sig["pcr_volume"] - 2.5) < 1e-9


def test_flat_smile_gives_zero_skew():
    rows, asof = _synthetic_chain(put_iv_bump=0.0)
    sig = opt.compute_signals(rows, asof=asof)
    assert abs(sig["skew_25d"]) < 1e-9


def test_empty_and_zero_dte_return_nan():
    # Empty chain.
    empty = opt.compute_signals(pd.DataFrame(
        columns=["underlying", "occ", "expiry", "right", "strike", "iv", "delta",
                 "bid", "ask", "mid", "volume"]))
    assert empty["expiry"] is None
    assert not np.isfinite(empty["atm_iv"])
    # Only a 0DTE expiry available → skipped (min_dte), no qualifying expiry.
    rows, asof = _synthetic_chain()
    rows["expiry"] = asof                      # everything expires today
    sig = opt.compute_signals(rows, asof=asof)
    assert sig["expiry"] is None
