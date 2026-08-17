"""Schema + serialization: counts, the pass gate, and valid NDJSON / JUnit XML output."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from harness.schema import CheckResult, RunReport, ScenarioResult, Status


def _result(id_, status, **kw):
    return ScenarioResult(id_, status, kw.pop("ms", 1.0), checks=kw.pop("checks", []), **kw)


def _report(*results):
    return RunReport("run1", "suite1", {"os": "Test"}, list(results), "2020-01-01T00:00:00Z", 5.0)


def test_counts_and_pass_gate():
    r = _report(_result("a", Status.PASS), _result("b", Status.SKIP))
    assert r.counts() == {"PASS": 1, "FAIL": 0, "ERROR": 0, "SKIP": 1}
    assert r.passed is True                                 # skips don't fail a run

    r2 = _report(_result("a", Status.PASS), _result("c", Status.FAIL))
    assert r2.passed is False
    assert _report(_result("e", Status.ERROR)).passed is False


def test_ndjson_is_a_run_header_then_result_lines():
    r = _report(_result("a", Status.PASS, metrics={"x": 1.0}))
    lines = r.to_ndjson().strip().split("\n")
    head = json.loads(lines[0])
    assert head["type"] == "run" and head["counts"]["PASS"] == 1
    row = json.loads(lines[1])
    assert row["type"] == "result" and row["id"] == "a" and row["run_id"] == "run1"


def test_junit_xml_encodes_statuses():
    r = _report(
        _result("p", Status.PASS),
        _result("f", Status.FAIL, checks=[CheckResult("chk", False, "too slow")]),
        _result("e", Status.ERROR, error="boom"),
        _result("s", Status.SKIP),
    )
    root = ET.fromstring(r.to_junit_xml())
    assert root.tag == "testsuite"
    assert root.attrib["tests"] == "4"
    assert root.attrib["failures"] == "1" and root.attrib["errors"] == "1" and root.attrib["skipped"] == "1"
    kinds = {tc.attrib["name"]: [c.tag for c in tc] for tc in root}
    assert kinds["p"] == [] and kinds["f"] == ["failure"]
    assert kinds["e"] == ["error"] and kinds["s"] == ["skipped"]


def test_report_json_round_trips():
    r = _report(_result("a", Status.PASS, metrics={"x": 2.0}))
    parsed = json.loads(r.to_json())
    assert parsed["suite"] == "suite1" and parsed["results"][0]["metrics"]["x"] == 2.0
