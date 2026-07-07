"""Tests for the microstructure alpha lab — the known ground-truth IC, signal decay, no look-ahead,
and the cost-survival break-even that is the whole point."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import microstructure as ms


def test_simulate_embeds_the_target_ic():
    p = ms.simulate(n=60_000, ic=0.10, seed=1)
    realized = p["ofi"].corr(p["fwd_ret"])          # OFI predicts the next-step return
    assert abs(realized - 0.10) < 0.02


def test_ic_decays_with_horizon():
    p = ms.simulate(n=60_000, ic=0.10, seed=2)
    d = ms.ic_by_horizon(p, p["ofi"], horizons=(1, 10))
    assert d[1] > d[10] > 0                          # strongest one step out, decays (≈ IC/√h)


def test_real_signal_has_a_gross_edge_but_noise_does_not():
    p = ms.simulate(n=60_000, ic=0.10, seed=3)
    real = ms.event_driven_backtest(p, p["ofi"], cost_bps=0.0)
    noise = pd.Series(np.random.default_rng(0).standard_normal(len(p)), index=p.index)
    rnd = ms.event_driven_backtest(p, noise, cost_bps=0.0)
    assert real["gross_ir"] > 0.02                   # the OFI signal is genuinely predictive
    assert abs(rnd["gross_ir"]) < 0.01               # a random signal earns nothing (no look-ahead leak)


def test_costs_erode_the_edge_and_a_breakeven_exists():
    p = ms.simulate(n=60_000, ic=0.10, seed=4)
    free = ms.event_driven_backtest(p, p["ofi"], cost_bps=0.0)["net_sharpe"]
    dear = ms.event_driven_backtest(p, p["ofi"], cost_bps=2.0)["net_sharpe"]
    assert free > dear                               # more cost, less edge
    assert dear < 0                                  # a real signal dies to realistic taker cost


def test_study_reports_decay_sweep_and_verdict():
    s = ms.study(n=40_000, ic=0.10)
    assert len(s["ic_decay"]) >= 4
    assert len(s["cost_sweep"]) >= 5
    assert s["gross_sharpe"] > 0                      # predictive gross
    assert s["breakeven_cost_bps"] is not None       # ...but only tradable below a break-even cost
    assert "OFI" in s["verdict"] or "order-flow" in s["verdict"].lower()
