"""Runner: correct statuses, fault isolation, determinism, redaction, and artifacts."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

from harness.adapters import CallableAdapter, CommandAdapter
from harness.checks import MetricThreshold
from harness.runner import exit_code, run_suite
from harness.scenario import Scenario, Suite
from harness.schema import Status


def _pass(id_):
    return Scenario(id_, CallableAdapter(lambda seed: {"m": 10.0}), checks=[MetricThreshold("m", ">", 1)])


def test_all_pass_gives_clean_exit():
    report = run_suite(Suite("s", [_pass("a"), _pass("b")]))
    assert report.passed and exit_code(report) == 0
    assert [r.status for r in report.results] == [Status.PASS, Status.PASS]


def test_failed_check_is_FAIL_and_gates_exit():
    bad = Scenario("bad", CallableAdapter(lambda seed: {"m": 0.0}), checks=[MetricThreshold("m", ">", 1)])
    report = run_suite(Suite("s", [bad]))
    assert report.results[0].status is Status.FAIL
    assert not report.passed and exit_code(report) == 1


def test_adapter_crash_is_isolated_as_ERROR():
    class Exploding:
        def run(self, seed):
            raise RuntimeError("adapter died")
    suite = Suite("s", [Scenario("boom", Exploding()), _pass("after")])
    report = run_suite(suite)
    assert report.results[0].status is Status.ERROR         # isolated
    assert report.results[1].status is Status.PASS          # suite kept going


def test_skip_if_yields_SKIP_and_does_not_fail_the_run():
    skipped = Scenario("dev", CallableAdapter(lambda seed: {}), skip_if=lambda: "device not present")
    report = run_suite(Suite("s", [skipped]))
    assert report.results[0].status is Status.SKIP and report.results[0].error == "device not present"
    assert report.passed


def test_determinism_same_seed_same_metrics():
    import random
    sc = Scenario("mc", CallableAdapter(lambda seed: {"r": random.Random(seed).random()}), seed=5)
    a = run_suite(Suite("s", [sc])).results[0].metrics["r"]
    b = run_suite(Suite("s", [sc])).results[0].metrics["r"]
    assert a == b


def test_stdout_is_redacted_in_stored_results():
    prog = "print('token=SUPERSECRET123 contact a@b.com')"
    sc = Scenario("leak", CommandAdapter([sys.executable, "-c", prog]))
    result = run_suite(Suite("s", [sc])).results[0]
    assert "SUPERSECRET123" not in result.stdout and "a@b.com" not in result.stdout
    assert "<redacted" in result.stdout


def test_artifacts_are_written_and_junit_parses(tmp_path):
    report = run_suite(Suite("s", [_pass("a")]), artifacts_dir=tmp_path)
    for fname in ("results.ndjson", "junit.xml", "report.json"):
        assert (tmp_path / fname).exists()
    ET.fromstring((tmp_path / "junit.xml").read_text())     # well-formed XML
