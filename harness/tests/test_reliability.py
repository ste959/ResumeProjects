"""Determinism / flakiness gate: correct classification, flaky detection, quarantine."""

from __future__ import annotations

import pytest

from harness.checks import MetricThreshold
from harness.reliability import check_determinism, flakiness_report, gate_passes
from harness.scenario import Scenario, Suite
from harness.adapters import CallableAdapter


def _scn(id_, fn, threshold=1.0, tags=()):
    return Scenario(id_, CallableAdapter(fn), checks=[MetricThreshold("v", ">", threshold)], tags=list(tags))


def test_stable_pass_is_classified_stable():
    r = check_determinism(_scn("p", lambda s: {"v": 10.0}), repeats=4)
    assert r.classification == "stable_pass" and r.pass_count == 4 and not r.is_flaky


def test_reproducible_failure_is_stable_fail_not_flaky():
    r = check_determinism(_scn("f", lambda s: {"v": 0.0}), repeats=4)
    assert r.classification == "stable_fail" and r.pass_count == 0 and not r.is_flaky


def test_changing_verdict_is_detected_as_flaky():
    # A scenario whose verdict flips across runs (a counter crossing the threshold) — the enemy.
    counter = {"n": 0}
    def flip(seed):
        v = counter["n"]
        counter["n"] += 1
        return {"v": float(v)}
    r = check_determinism(_scn("flaky", flip, threshold=2.0), repeats=4)   # v = 0,1,2,3 → F,F,F,P
    assert r.classification == "flaky" and r.is_flaky


def test_varying_metric_is_reported_but_does_not_imply_flaky():
    counter = {"n": 0}
    def drift(seed):
        counter["n"] += 1
        return {"v": 100.0, "tick": float(counter["n"])}    # v constant (passes), tick varies
    r = check_determinism(_scn("d", drift), repeats=3)
    assert r.classification == "stable_pass"
    assert "tick" in r.varying_metrics and "v" not in r.varying_metrics


def test_alternating_fail_and_error_is_flaky_not_stable_fail():
    # Verdict flips between FAIL (check fails) and ERROR (adapter crashes) — genuine instability that
    # must be caught, not collapsed into stable_fail and waved through the gate.
    counter = {"n": 0}
    def flip(seed):
        n = counter["n"]; counter["n"] += 1
        if n % 2 == 0:
            raise RuntimeError("crash")          # → ERROR
        return {"v": 0.0}                         # → FAIL (v > 1 fails)
    r = check_determinism(_scn("fe", flip, threshold=1.0), repeats=4)
    assert r.classification == "flaky" and r.is_flaky


def test_all_skips_classify_as_skipped():
    scn = Scenario("dev", CallableAdapter(lambda s: {}), skip_if=lambda: "device absent")
    r = check_determinism(scn, repeats=3)
    assert r.classification == "skipped" and not r.is_flaky


def test_check_determinism_needs_at_least_two_repeats():
    with pytest.raises(ValueError):
        check_determinism(_scn("p", lambda s: {"v": 10.0}), repeats=1)


def test_gate_fails_only_on_flaky():
    counter = {"n": 0}
    def flip(seed):
        v = counter["n"]; counter["n"] += 1; return {"v": float(v)}
    suite = Suite("s", [_scn("ok", lambda s: {"v": 9.0}), _scn("bad", flip, threshold=2.0)])
    reports = flakiness_report(suite, repeats=4)
    assert not gate_passes(reports)                          # the flaky one fails the gate
    assert gate_passes([r for r in reports if r.scenario_id == "ok"])


def test_flakiness_report_skips_quarantined_tags():
    suite = Suite("s", [_scn("a", lambda s: {"v": 9.0}),
                        _scn("q", lambda s: {"v": 9.0}, tags=["quarantine"])])
    reports = flakiness_report(suite, repeats=2, skip_tags={"quarantine"})
    assert [r.scenario_id for r in reports] == ["a"]         # quarantined one not probed
