"""Checks: each assertion passes/fails as specified."""

from __future__ import annotations

import pytest

from harness.adapters import AdapterOutcome
from harness.checks import ExitZero, MetricPresent, MetricThreshold, NoError, OutputContains


def _out(**kw):
    return AdapterOutcome(ok=kw.pop("ok", True), **kw)


def test_exit_zero():
    assert ExitZero().evaluate(_out(exit_code=0)).ok
    assert not ExitZero().evaluate(_out(exit_code=1)).ok


def test_no_error():
    assert NoError().evaluate(_out(ok=True)).ok
    assert not NoError().evaluate(_out(ok=False, error="x")).ok


def test_output_contains():
    assert OutputContains("ready").evaluate(_out(stdout="system ready")).ok
    assert not OutputContains("ready").evaluate(_out(stdout="nope")).ok


def test_metric_present():
    assert MetricPresent("t").evaluate(_out(metrics={"t": 1})).ok
    assert not MetricPresent("t").evaluate(_out(metrics={})).ok


@pytest.mark.parametrize("op, value, metric, expected", [
    (">", 100.0, 150.0, True), (">", 100.0, 50.0, False),
    ("<", 50_000.0, 1_800.0, True), ("==", 42.0, 42.0, True), (">=", 5.0, 5.0, True),
])
def test_metric_threshold(op, value, metric, expected):
    assert MetricThreshold("m", op, value).evaluate(_out(metrics={"m": metric})).ok is expected


def test_metric_threshold_missing_metric_fails():
    assert not MetricThreshold("absent", ">", 0).evaluate(_out(metrics={})).ok


def test_metric_threshold_rejects_unknown_operator():
    with pytest.raises(ValueError):
        MetricThreshold("m", "≈", 1.0)
