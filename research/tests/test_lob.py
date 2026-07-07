"""Tests for the microstructure feature/label harness — the properties that matter are
leakage-freeness and causal (time-ordered) splits, not any particular signal."""

from __future__ import annotations

import numpy as np

from mds import lob


def test_information_coefficient_recovers_sign():
    rng = np.random.default_rng(0)
    x = np.arange(200.0)
    y = x + rng.normal(0, 5, 200)  # positively correlated
    ic = lob.information_coefficient(x, y)
    assert ic["pearson"] > 0.9
    assert ic["spearman"] > 0.9

    z = -x + rng.normal(0, 5, 200)  # negatively correlated
    assert lob.information_coefficient(x, z)["pearson"] < -0.9


def test_information_coefficient_handles_degenerate_input():
    ic = lob.information_coefficient(np.ones(50), np.arange(50.0))  # zero-variance feature
    assert np.isnan(ic["pearson"])


def test_walk_forward_splits_are_causal_and_disjoint():
    n = 200
    seen_any = False
    for train, test in lob.walk_forward_splits(n, folds=4):
        seen_any = True
        assert train.max() < test.min()                 # train strictly precedes test in time
        assert len(np.intersect1d(train, test)) == 0     # no overlap
        assert test.min() == train.max() + 1             # contiguous, no gaps
    assert seen_any


def test_panel_is_leakage_free(tmp_path):
    # A tiny two-sided L2 session: a full snapshot + a trade each tick.
    lines = ["seq,ts,product,kind,side,price,size"]
    for t in range(40):
        ts = f"2020-01-01T00:00:{t:02d}Z"
        mid = 100 + 0.02 * t
        lines.append(f"{t + 1},{ts},X,SNAP,B,{mid - 0.05:.4f},5")
        lines.append(f"{t + 1},{ts},X,SNAP,A,{mid + 0.05:.4f},5")
        lines.append(f"{2000 + t},{ts},X,TRD,B,{mid:.4f},0.1")
    path = tmp_path / "l2-tiny.csv"
    path.write_text("\n".join(lines) + "\n")

    horizon = 5
    df = lob.build_panel(path, product="X", sample_every=1, horizon=horizon, depth=2)

    assert len(df) > 0
    # No look-ahead: the tail with no observable future is dropped, so every label is real.
    assert df["fwd_ret"].notna().all()
    assert set(lob.FEATURES).issubset(df.columns)
    # The mid rose monotonically, so every forward return is positive.
    assert (df["fwd_ret"] > 0).all()
