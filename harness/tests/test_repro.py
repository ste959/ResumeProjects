"""Repro bundles: written for failures only, self-contained, redacted, with a rerun command."""

from __future__ import annotations

import json
import sys

from harness.adapters import CallableAdapter, CommandAdapter
from harness.checks import ExitZero, MetricThreshold
from harness.runner import run_suite
from harness.scenario import Scenario, Suite


def _failing():
    return Scenario("bad", CallableAdapter(lambda s: {"v": 0.0}),
                    checks=[MetricThreshold("v", ">", 1)], seed=42, tags=["demo"])


def test_bundle_written_only_for_failures(tmp_path):
    suite = Suite("s", [Scenario("good", CallableAdapter(lambda s: {"v": 9.0}),
                                 checks=[MetricThreshold("v", ">", 1)]), _failing()])
    report = run_suite(suite, repro_dir=tmp_path)
    run_dir = tmp_path / report.run_id
    assert (run_dir / "bad").is_dir()               # failure bundled
    assert not (run_dir / "good").exists()          # pass not bundled


def test_bundle_is_self_contained(tmp_path):
    report = run_suite(Suite("s", [_failing()]), repro_dir=tmp_path)
    bundle = tmp_path / report.run_id / "bad"
    for f in ("bundle.json", "stdout.log", "stderr.log", "REPRODUCE.txt"):
        assert (bundle / f).exists()
    manifest = json.loads((bundle / "bundle.json").read_text())
    assert manifest["seed"] == 42 and manifest["status"] == "FAIL"
    assert manifest["scenario"] == "bad" and "environment" in manifest
    failed = [c for c in manifest["checks"] if not c["ok"]]
    assert failed and "repro_command" in manifest
    assert "Reproduce scenario 'bad'" in (bundle / "REPRODUCE.txt").read_text()


def test_bundle_output_is_redacted(tmp_path):
    prog = "print('token=SUPERSECRET contact a@b.com'); import sys; sys.exit(1)"
    scn = Scenario("leaky", CommandAdapter([sys.executable, "-c", prog]), checks=[ExitZero()])
    report = run_suite(Suite("s", [scn]), repro_dir=tmp_path)
    stdout = (tmp_path / report.run_id / "leaky" / "stdout.log").read_text()
    assert "SUPERSECRET" not in stdout and "a@b.com" not in stdout


def test_command_repro_pins_the_seed(tmp_path):
    prog = "import os; raise SystemExit(1)"
    scn = Scenario("cmd", CommandAdapter([sys.executable, "-c", prog]), seed=77, checks=[ExitZero()])
    report = run_suite(Suite("s", [scn]), repro_dir=tmp_path)
    manifest = json.loads((tmp_path / report.run_id / "cmd" / "bundle.json").read_text())
    assert "LAB_SEED=77" in manifest["repro_command"]        # exact, seed-pinned command
