"""Quality gates: capture/round-trip, and status / accuracy / performance regression detection —
including the hardware-aware downgrade of perf regressions across a machine mismatch."""

from __future__ import annotations

import pytest

from harness.baseline import (Baseline, BaselinePolicy, MetricRule, capture_baseline,
                              compare_to_baseline)
from harness.schema import RunReport, ScenarioResult, Status

_X86 = {"os": "Linux", "arch": "x86_64"}
_ARM = {"os": "Linux", "arch": "arm64"}


def _result(id_, status, metrics):
    return ScenarioResult(id_, status, 1.0, metrics=metrics)


def _report(env, *results):
    return RunReport("run1", "example", env, list(results), "2020-01-01T00:00:00Z", 1.0)


def _policy():
    return BaselinePolicy({"pi": MetricRule("exact", 0.05), "tput": MetricRule("higher", 0.30)})


# ---- rules + capture/round-trip --------------------------------------------
def test_metric_rule_directions():
    assert MetricRule("higher", 0.2).regressed(100, 70)          # dropped 30% > 20%
    assert not MetricRule("higher", 0.2).regressed(100, 90)
    assert MetricRule("lower", 0.2).regressed(100, 130)          # rose 30% > 20%
    assert MetricRule("exact", 0.05).regressed(3.14, 3.30)       # |Δ| 0.16 > 0.05
    with pytest.raises(ValueError):
        MetricRule("sideways", 0.1)


def test_capture_and_round_trip(tmp_path):
    report = _report(_X86, _result("a", Status.PASS, {"tput": 1000.0}))
    base = capture_baseline(report)
    assert base.scenarios["a"] == {"status": "PASS", "metrics": {"tput": 1000.0}}
    path = base.save(tmp_path / "b.json")
    reloaded = Baseline.load(path)
    assert reloaded.scenarios == base.scenarios and reloaded.environment == _X86


# ---- regressions ------------------------------------------------------------
def test_no_change_is_clean():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {"tput": 1000.0, "pi": 3.14})))
    now = _report(_X86, _result("a", Status.PASS, {"tput": 1000.0, "pi": 3.14}))
    assert compare_to_baseline(now, base, _policy()).passed


def test_status_regression_gates():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {})))
    now = _report(_X86, _result("a", Status.FAIL, {}))
    cmp = compare_to_baseline(now, base, _policy())
    assert not cmp.passed and cmp.regressions[0].kind == "status"


def test_pass_to_skip_is_a_note_not_a_regression():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {})))
    now = _report(_X86, _result("a", Status.SKIP, {}))
    cmp = compare_to_baseline(now, base, _policy())
    assert cmp.passed and any("now SKIP" in n for n in cmp.notes)


def test_accuracy_regression_gates_even_across_hardware():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {"pi": 3.14})))
    now = _report(_ARM, _result("a", Status.PASS, {"pi": 2.5}))       # drifted 0.64 > 0.05, different HW
    cmp = compare_to_baseline(now, base, _policy())
    assert not cmp.passed and cmp.regressions[0].kind == "accuracy"   # accuracy is portable


def test_performance_regression_gates_on_same_hardware():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {"tput": 1000.0})))
    now = _report(_X86, _result("a", Status.PASS, {"tput": 500.0}))   # 50% drop > 30% tol
    cmp = compare_to_baseline(now, base, _policy())
    assert not cmp.passed and cmp.regressions[0].kind == "performance"


def test_performance_regression_downgrades_across_hardware():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {"tput": 1000.0})))
    now = _report(_ARM, _result("a", Status.PASS, {"tput": 500.0}))   # big drop, but different CPU
    cmp = compare_to_baseline(now, base, _policy())
    assert cmp.passed                                                # NOT gated across hardware
    assert not cmp.hardware_comparable and any("perf drift" in n for n in cmp.notes)


def test_missing_metric_is_a_regression():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {"tput": 1000.0})))
    now = _report(_X86, _result("a", Status.PASS, {}))               # metric disappeared, same HW
    cmp = compare_to_baseline(now, base, _policy())
    assert not cmp.passed and cmp.regressions[0].kind == "missing"


def test_missing_perf_metric_is_a_note_across_hardware():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {"tput": 1000.0})))
    now = _report(_ARM, _result("a", Status.PASS, {}))               # absent, but different CPU
    cmp = compare_to_baseline(now, base, _policy())
    assert cmp.passed and any("perf metric absent" in n for n in cmp.notes)  # not gated cross-hardware


def test_new_and_removed_scenarios_are_notes():
    base = capture_baseline(_report(_X86, _result("gone", Status.PASS, {})))
    now = _report(_X86, _result("fresh", Status.PASS, {}))
    cmp = compare_to_baseline(now, base, _policy())
    assert cmp.passed
    assert any("scenario removed" in n for n in cmp.notes)
    assert any("new scenario" in n for n in cmp.notes)


def test_unruled_metrics_never_gate():
    base = capture_baseline(_report(_X86, _result("a", Status.PASS, {"samples": 20000.0})))
    now = _report(_X86, _result("a", Status.PASS, {"samples": 5.0}))  # huge change, but no rule
    assert compare_to_baseline(now, base, BaselinePolicy()).passed
