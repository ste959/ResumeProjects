"""Tests for the capacity/crowding layer — the model's behaviour is provable, so we pin the
properties that make it trustworthy: capacity maximises profit, water-filling beats concentration
and equalises marginal profit, and crowding is a genuine tragedy of the commons."""

from __future__ import annotations

import numpy as np

from mds import capacity as cap


def test_optimal_capacity_maximizes_single_signal_profit():
    mu, lam = 0.10, 0.05
    cstar = cap.optimal_capacity(mu, lam)          # μ/2λ = 1.0
    p = cap.total_profit([mu], [lam], [cstar])
    for delta in (-0.2, -0.05, 0.05, 0.2):
        assert cap.total_profit([mu], [lam], [cstar + delta]) < p


def test_capacity_aware_beats_concentrate_and_respects_budget():
    mu = np.array([0.10, 0.10, 0.10])
    lam = np.array([0.02, 0.10, 0.50])   # same edge, very different capacity
    budget = 3.0
    aware = cap.allocate_with_capacity(mu, lam, budget)
    naive = cap.concentrate(mu, budget)
    assert abs(aware.sum() - budget) < 1e-6     # deploys the whole budget
    assert (aware >= -1e-9).all()               # no negative capital
    assert cap.total_profit(mu, lam, aware) > cap.total_profit(mu, lam, naive)


def test_water_filling_equalizes_marginal_profit_on_funded_signals():
    # When every signal is funded, KKT says marginal profit μ_i − 2λ_i·C_i is equal across them.
    mu = np.array([0.12, 0.10, 0.08])
    lam = np.array([0.02, 0.05, 0.03])
    C = cap.allocate_with_capacity(mu, lam, budget=2.0)
    assert (C > 0).all()
    marginals = mu - 2.0 * lam * C
    assert marginals.std() < 1e-3


def test_crowding_is_a_tragedy_of_the_commons():
    mu, lam = 0.10, 0.05
    solo = cap.crowding_equilibrium(mu, lam, 1)
    assert abs(solo["capital_each"] - cap.optimal_capacity(mu, lam)) < 1e-9   # K=1 = monopoly
    assert abs(solo["aggregate_profit"] - mu ** 2 / (4 * lam)) < 1e-9

    prev = solo
    for k in (2, 4, 8, 16):
        e = cap.crowding_equilibrium(mu, lam, k)
        assert e["total_capital"] > prev["total_capital"]        # crowd deploys more capital...
        assert e["rate"] < prev["rate"]                          # ...eroding the shared rate...
        assert e["aggregate_profit"] < prev["aggregate_profit"]  # ...and destroying total profit
        prev = e


def test_negative_edge_signal_gets_no_capital():
    # A losing signal has C* = μ/2λ < 0; sizing to capacity (clipped at 0) simply won't fund it.
    mu = np.array([0.03, -0.05])
    lam = np.array([0.04, 0.02])
    alloc = np.clip(cap.optimal_capacity(mu, lam), 0.0, None)
    assert alloc[0] > 0
    assert alloc[1] == 0.0
