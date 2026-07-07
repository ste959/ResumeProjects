"""Tests for the regime-conditional factor-timing overlay — the tilt reduces to the endpoints at
the regime extremes, the timed composite stays a valid standardized cross-section, and exposure
timing / risk budgeting are causal (no look-ahead)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import factortiming as ft


def _score(vals):
    idx = pd.date_range("2021-01-01", periods=len(vals))
    return pd.Series(vals, index=idx)


def test_regime_weights_interpolate_to_endpoints():
    s = _score([0.0, 1.0, 0.5])
    fams = ["value", "quality", "low_risk", "momentum"]
    w = ft.regime_family_weights(s, fams)
    for fam in fams:
        assert abs(w[fam].iloc[0] - ft.RISK_OFF_TILT[fam]) < 1e-9    # score 0 → risk-off tilt
        assert abs(w[fam].iloc[1] - ft.RISK_ON_TILT[fam]) < 1e-9     # score 1 → risk-on tilt
        mid = 0.5 * (ft.RISK_OFF_TILT[fam] + ft.RISK_ON_TILT[fam])
        assert abs(w[fam].iloc[2] - mid) < 1e-9


def test_risk_off_upweights_defensive_vs_cyclical():
    # In deep risk-off, low_risk should carry more weight than momentum; risk-on flips it.
    off = ft.regime_family_weights(_score([0.0]), ["low_risk", "momentum"])
    on = ft.regime_family_weights(_score([1.0]), ["low_risk", "momentum"])
    assert off["low_risk"].iloc[0] > off["momentum"].iloc[0]
    assert on["momentum"].iloc[0] > on["low_risk"].iloc[0]


def test_timed_composite_is_standardized():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2021-01-01", periods=30)
    cols = list("ABCDE")
    fam_scores = {f: pd.DataFrame(rng.normal(size=(30, 5)), index=idx, columns=cols)
                  for f in ("value", "quality", "momentum", "low_risk")}
    score = pd.Series(rng.uniform(0, 1, 30), index=idx)
    comp = ft.timed_composite(fam_scores, score)
    assert comp.mean(axis=1).abs().max() < 1e-9
    assert (comp.std(axis=1).dropna() - 1.0).abs().max() < 1e-6    # sample (ddof=1) std


def test_apply_regime_exposure_scales_and_is_causal():
    idx = pd.date_range("2021-01-01", periods=10)
    rets = pd.Series(0.01, index=idx)
    score = pd.Series(0.5, index=idx)
    timed = ft.apply_regime_exposure(rets, score)
    assert np.allclose(timed.dropna(), 0.005)               # scaled by 0.5
    # zero score fully de-risks
    assert np.allclose(ft.apply_regime_exposure(rets, pd.Series(0.0, index=idx)).dropna(), 0.0)


def test_risk_budget_no_lookahead():
    # A vol spike must not change sizing BEFORE it happens (causal vol-target).
    idx = pd.date_range("2021-01-01", periods=120)
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0, 0.01, 120), index=idx)
    r.iloc[60:] *= 5.0                                        # regime shift to high vol at day 60
    scaled = ft.risk_budget(r, target_annual_vol=0.10)
    # the scale applied at day 40 (calm) must be identical whether or not the later spike exists
    r2 = r.copy(); r2.iloc[60:] = rng.normal(0, 0.05, 60)
    s1 = ft.risk_budget(r, target_annual_vol=0.10).iloc[40]
    s2 = ft.risk_budget(r2, target_annual_vol=0.10).iloc[40]
    assert abs(s1 - s2) < 1e-12
