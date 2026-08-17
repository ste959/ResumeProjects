"""A deterministic validation harness — a small "readiness lab" for systems under test.

It drives a system under test (an in-process function or an external command), asserts checks against
its output, and produces comparable, machine-readable results (NDJSON telemetry, JUnit XML, a JSON
report). Designed around the parts a real validation lab needs: packaged scenario collateral, pluggable
harness adapters, deterministic execution, confidential-data redaction, and a CI-friendly exit gate.

    from harness import Scenario, Suite, CallableAdapter, MetricThreshold, run_suite, exit_code

    suite = Suite("smoke", [
        Scenario("adds", CallableAdapter(lambda seed: {"sum": 2 + 2}),
                 checks=[MetricThreshold("sum", "==", 4)]),
    ])
    report = run_suite(suite, artifacts_dir="artifacts")
    raise SystemExit(exit_code(report))
"""

from __future__ import annotations

from .adapters import AdapterOutcome, CallableAdapter, CommandAdapter
from .checks import ExitZero, MetricPresent, MetricThreshold, NoError, OutputContains
from .runner import exit_code, run_suite, write_artifacts
from .scenario import Scenario, Suite
from .schema import CheckResult, RunReport, ScenarioResult, Status
from .telemetry import environment_fingerprint, redact

__all__ = [
    "Scenario", "Suite",
    "CallableAdapter", "CommandAdapter", "AdapterOutcome",
    "ExitZero", "NoError", "OutputContains", "MetricPresent", "MetricThreshold",
    "run_suite", "write_artifacts", "exit_code",
    "RunReport", "ScenarioResult", "CheckResult", "Status",
    "environment_fingerprint", "redact",
]
