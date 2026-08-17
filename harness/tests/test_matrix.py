"""Config-matrix orchestration: config reaches the SUT, env is restored, and the grid surfaces
config-dependent failures."""

from __future__ import annotations

import json
import os

from harness.adapters import CallableAdapter
from harness.checks import MetricPresent, MetricThreshold
from harness.matrix import Matrix, run_matrix
from harness.scenario import Scenario, Suite
from harness.schema import Status


def _mode_metric(seed):
    return {"v": float(os.environ.get("LAB_TEST_MODE", "0"))}


def _budget(seed):
    return {"budget": float({"lo": 100, "hi": 200}.get(os.environ.get("LAB_TEST_MODE", "lo"), 100))}


def test_config_reaches_the_sut_and_is_restored():
    assert "LAB_TEST_MODE" not in os.environ
    suite = Suite("s", [Scenario("p", CallableAdapter(_mode_metric), checks=[MetricPresent("v")])])
    matrix = Matrix("m", {"a": {"LAB_TEST_MODE": "1"}, "b": {"LAB_TEST_MODE": "2"}})
    report = run_matrix(suite, matrix)
    assert report.metric_grid("v") == {"p": {"a": 1.0, "b": 2.0}}   # the config reached the SUT
    assert "LAB_TEST_MODE" not in os.environ                        # …and the environment was restored


def test_existing_env_value_is_restored():
    os.environ["LAB_TEST_MODE"] = "original"
    try:
        suite = Suite("s", [Scenario("p", CallableAdapter(_mode_metric), checks=[MetricPresent("v")])])
        run_matrix(suite, Matrix("m", {"a": {"LAB_TEST_MODE": "override"}}))
        assert os.environ["LAB_TEST_MODE"] == "original"            # restored to prior value, not popped
    finally:
        del os.environ["LAB_TEST_MODE"]


def test_status_grid_and_no_failures():
    suite = Suite("s", [Scenario("ok", CallableAdapter(lambda s: {"v": 1.0}), checks=[MetricPresent("v")])])
    report = run_matrix(suite, Matrix("m", {"a": {}, "b": {}}))
    grid = report.status_grid()
    assert grid == {"ok": {"a": Status.PASS, "b": Status.PASS}}
    assert not report.any_failure() and report.divergent_scenarios() == []


def test_config_dependent_failure_is_surfaced():
    suite = Suite("s", [
        Scenario("probe", CallableAdapter(_budget), checks=[MetricPresent("budget")]),
        Scenario("needs_high", CallableAdapter(_budget), checks=[MetricThreshold("budget", ">=", 150)]),
    ])
    matrix = Matrix("m", {"lo": {"LAB_TEST_MODE": "lo"}, "hi": {"LAB_TEST_MODE": "hi"}})
    report = run_matrix(suite, matrix)

    assert report.divergent_scenarios() == ["needs_high"]           # config-dependent
    grid = report.status_grid()
    assert grid["needs_high"]["lo"] is Status.FAIL and grid["needs_high"]["hi"] is Status.PASS
    assert grid["probe"]["lo"] is Status.PASS and grid["probe"]["hi"] is Status.PASS
    assert report.any_failure()
    assert report.metric_grid("budget") == {"probe": {"lo": 100.0, "hi": 200.0},
                                            "needs_high": {"lo": 100.0, "hi": 200.0}}


def test_to_json_is_parseable_and_records_divergence():
    suite = Suite("s", [Scenario("needs_high", CallableAdapter(_budget),
                                 checks=[MetricThreshold("budget", ">=", 150)])])
    report = run_matrix(suite, Matrix("m", {"lo": {"LAB_TEST_MODE": "lo"}, "hi": {"LAB_TEST_MODE": "hi"}}))
    doc = json.loads(report.to_json())
    assert doc["matrix"] == "m" and doc["divergent"] == ["needs_high"]
    assert doc["status_grid"]["needs_high"] == {"lo": "FAIL", "hi": "PASS"}
