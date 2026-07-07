"""Offline tests for the research service's compute layer — the pure JSON helpers and metadata,
plus (if FastAPI is installed) that the routes are registered. Deliberately data-free so it runs in
CI without the gitignored warehouse: the data-dependent compute functions are exercised by the
existing mds tests and by run_construction.py, not here."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from service import compute


def test_f_handles_nonfinite():
    assert compute._f(1.5) == 1.5
    assert compute._f(float("nan")) is None
    assert compute._f(float("inf")) is None
    assert compute._f(None) is None


def test_curve_downsamples_and_shapes():
    idx = pd.date_range("2021-01-01", periods=1000)
    net = pd.Series(np.random.default_rng(0).normal(0, 0.01, 1000), index=idx)
    curve = compute._curve(net, points=180)
    assert 120 <= len(curve) <= 210               # ≈180 samples after striding
    assert set(curve[0]) == {"date", "value"}
    assert isinstance(curve[0]["value"], float)


def test_signal_meta_is_consistent():
    valid_families = set(compute.FAMILY_ROLE) | {"composite"}
    for name, meta in compute.SIGNAL_META.items():
        assert meta["family"] in valid_families, name
        assert meta["label"] and meta["desc"]


def test_app_routes_registered():
    pytest.importorskip("fastapi")
    from service import app as service_app
    paths = {r.path for r in service_app.app.routes}
    for p in ("/api/research/health", "/api/research/signals", "/api/research/backtest",
              "/api/research/findings", "/api/research/construction"):
        assert p in paths
