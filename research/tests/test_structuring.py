"""Tests for the options structuring overlay — the Black–Scholes core must satisfy put–call parity
and delta bounds, and the structures must price/select sensibly (higher IV → richer premium,
overwrite picks the weak-momentum names)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import structuring as st


def test_put_call_parity():
    S, K, T, sig, r = 100.0, 105.0, 0.5, 0.25, 0.04
    c = st.bs_price(S, K, T, sig, r, "call")
    p = st.bs_price(S, K, T, sig, r, "put")
    assert abs((c - p) - (S - K * np.exp(-r * T))) < 1e-8


def test_delta_bounds_and_signs():
    assert 0.0 <= st.bs_delta(100, 100, 0.5, 0.2, kind="call") <= 1.0
    assert -1.0 <= st.bs_delta(100, 100, 0.5, 0.2, kind="put") <= 0.0
    # deep ITM call → delta ≈ 1; deep OTM put → delta ≈ 0
    assert st.bs_delta(200, 100, 0.5, 0.2, kind="call") > 0.95
    assert st.bs_delta(200, 100, 0.5, 0.2, kind="put") > -0.05


def test_price_zero_at_expiry_is_intrinsic():
    assert abs(st.bs_price(110, 100, 0.0, 0.2, kind="call") - 10.0) < 1e-9
    assert abs(st.bs_price(90, 100, 0.0, 0.2, kind="put") - 10.0) < 1e-9


def test_protective_put_costs_more_at_higher_iv():
    lo = st.protective_put(100, 0.15, 30)["premium"]
    hi = st.protective_put(100, 0.45, 30)["premium"]
    assert hi > lo > 0


def test_covered_call_income_positive_and_caps_upside():
    cc = st.covered_call(100, 0.30, 30, moneyness=1.05)
    assert cc["premium"] > 0
    assert cc["annual_income"] > 0
    assert 0.0 < cc["upside_cap_pct"] < 0.1


def test_collar_net_cost_is_put_minus_call():
    col = st.collar(100, 0.30, 45, put_moneyness=0.9, call_moneyness=1.1)
    assert abs(col["net_cost"] - (col["put_premium"] - col["call_premium"])) < 1e-9


def test_variance_premium_sign():
    rich = st.variance_premium(0.30, 0.20)
    cheap = st.variance_premium(0.15, 0.25)
    assert rich["sells_rich"] and rich["vrp_vol"] > 0
    assert not cheap["sells_rich"] and cheap["vrp_vol"] < 0


def test_tail_hedge_sleeve_scales_with_book():
    surface = pd.DataFrame({"symbol": ["A", "B", "C"], "atm_iv": [0.2, 0.25, 0.3],
                            "dte": [30, 30, 30], "skew_25d": [0.02, 0.03, 0.01]})
    small = st.tail_hedge_sleeve(1e6, surface)
    big = st.tail_hedge_sleeve(1e7, surface)
    assert small["ok"] and big["ok"]
    assert abs(big["sleeve_cost"] / small["sleeve_cost"] - 10.0) < 1e-6
    assert big["cheap_entry_annual_drag"] <= big["annual_drag"] + 1e-12   # low-IV entry is cheaper


def test_overwrite_prefers_weak_momentum_high_iv():
    positions = pd.Series({"A": 100.0, "B": 100.0, "C": 100.0, "D": 100.0})
    surface = pd.DataFrame({"symbol": ["A", "B", "C", "D"],
                            "atm_iv": [0.5, 0.5, 0.2, 0.2], "dte": [30, 30, 30, 30]})
    momentum = pd.Series({"A": -2.0, "B": 2.0, "C": -2.0, "D": 2.0})   # A,C weak; B,D strong
    cand = st.overwrite_candidates(positions, surface, momentum, momentum_quantile=0.5)
    picked = set(cand["symbol"])
    assert "A" in picked                          # weak momentum + high IV → top candidate
    assert "B" not in picked and "D" not in picked  # strong momentum excluded
    assert cand.iloc[0]["symbol"] == "A"          # highest IV among weak names ranks first
