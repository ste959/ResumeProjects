"""Tests for the multi-factor composite — the properties that make combining signals honest:
standardization, NaN-skipping blend (a name missing one input is still scored), and that a composite
built from a return-predictive signal actually shows positive information coefficient."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import factors as fc


def _frame(seed, cols=("A", "B", "C", "D", "E"), n=40):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n)
    return pd.DataFrame(rng.normal(size=(n, len(cols))), index=idx, columns=list(cols))


def test_standardize_demeans_and_unit_variance_each_day():
    z = fc.standardize(_frame(0))
    assert z.mean(axis=1).abs().max() < 1e-9
    assert (z.std(axis=1) - 1.0).abs().max() < 1e-6      # sample (ddof=1) std, matching _xs_zscore


def test_winsorize_clips_outliers():
    f = _frame(1)
    f.iloc[0, 0] = 1e6                     # a wild outlier
    z = fc.standardize(f, winsor=3.0)
    assert z.abs().max().max() <= 3.0 + 1e-6


def test_blend_skips_nan_so_partial_names_still_scored():
    a = _frame(2)
    b = _frame(3)
    b.iloc[:, 0] = np.nan                  # column A missing entirely from input b
    out = fc.blend([a, b])
    assert out["A"].notna().all()          # A still scored (from a alone)
    # where both present, blend equals the simple mean
    assert np.allclose(out["B"], (a["B"] + b["B"]) / 2.0)


def test_family_scores_only_builds_present_families():
    sigs = {"earnings_yield": _frame(4), "momentum": _frame(5), "roe": _frame(6)}
    fams = fc.family_scores(sigs)
    assert "value" in fams and "quality" in fams and "momentum" in fams
    assert "flow" not in fams               # no flow members supplied
    for f in fams.values():
        assert f.mean(axis=1).abs().max() < 1e-9


def test_composite_is_standardized_and_weightable():
    sigs = {"earnings_yield": _frame(7), "momentum": _frame(8), "low_vol": _frame(9)}
    comp = fc.composite(sigs)
    assert comp.mean(axis=1).abs().max() < 1e-9
    # a value-only weighting should track the value family, not the momentum one
    val_only = fc.composite(sigs, weights={"value": 1.0, "momentum": 0.0, "low_risk": 0.0})
    fam = fc.family_scores(sigs)["value"]
    corr = val_only.iloc[-1].corr(fam.iloc[-1])
    assert corr > 0.99


def test_ic_positive_for_a_return_predictive_score():
    # Build returns, then a score that is next-day return + noise → should have positive mean IC.
    rng = np.random.default_rng(11)
    idx = pd.date_range("2021-01-01", periods=120)
    cols = list("ABCDEFGH")
    rets = pd.DataFrame(rng.normal(0, 0.01, (120, len(cols))), index=idx, columns=cols)
    # score at t carries next-day return: ic_series lags it one day, so score_{t-1} (≈ ret_t) is
    # correlated with ret_t → positive IC, without any actual look-ahead in the measurement.
    score = rets.shift(-1) + rng.normal(0, 0.005, (120, len(cols)))
    ic = fc.ic_series(score, rets)
    summ = fc.ic_summary(ic)
    assert summ["mean_ic"] > 0
    assert summ["n"] > 50
