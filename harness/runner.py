"""The deterministic runner — executes a suite and produces a :class:`~harness.schema.RunReport`.

Guarantees that make a run trustworthy:

* **Fault isolation.** A scenario whose adapter crashes becomes an ERROR *result*; the suite finishes.
  One broken scenario never aborts the run.
* **Correct status.** An infra fault (adapter couldn't run the SUT) is ERROR; a SUT that ran but failed
  a check is FAIL; a precondition not met is SKIP. Only PASS/SKIP count as a clean run.
* **Determinism.** Scenarios run in declared order, each under its fixed seed, so a run is reproducible.
* **Confidential-data hygiene.** Captured stdout/stderr is redacted before it is stored.

Artifacts (NDJSON telemetry, JUnit XML, JSON report) are written for CI and archival, and
:func:`exit_code` turns a report into a process exit status for a build gate.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from .adapters import AdapterOutcome
from .scenario import Scenario, Suite
from .schema import RunReport, ScenarioResult, Status
from .telemetry import Timer, environment_fingerprint, now_iso, redact


def _safe_run(adapter, seed: int) -> AdapterOutcome:
    try:
        return adapter.run(seed)
    except Exception as e:                       # noqa: BLE001 — isolate a misbehaving adapter
        return AdapterOutcome(ok=False, error=f"adapter crashed: {type(e).__name__}: {e}")


def _describe(adapter, seed: int) -> str:
    describe = getattr(adapter, "describe", None)
    try:
        return describe(seed) if callable(describe) else ""
    except Exception:                            # never let repro-info gathering break a run
        return ""


def _status(outcome: AdapterOutcome, checks) -> Status:
    if not outcome.ok:
        return Status.ERROR                      # the SUT never really ran
    return Status.PASS if all(c.ok for c in checks) else Status.FAIL


def _run_one(scenario: Scenario, *, redact_output: bool,
             skip_tags: frozenset[str] = frozenset()) -> ScenarioResult:
    started = now_iso()
    repro = _describe(scenario.adapter, scenario.seed)

    quarantined = skip_tags.intersection(scenario.tags)
    if quarantined:
        return ScenarioResult(scenario.id, Status.SKIP, 0.0, seed=scenario.seed,
                              tags=list(scenario.tags), error=f"quarantined ({', '.join(sorted(quarantined))})",
                              repro=repro, started_at=started)
    if scenario.skip_if is not None:
        reason = scenario.skip_if()
        if reason:
            return ScenarioResult(scenario.id, Status.SKIP, 0.0, seed=scenario.seed,
                                  tags=list(scenario.tags), error=reason, repro=repro, started_at=started)

    with Timer() as t:
        outcome = _safe_run(scenario.adapter, scenario.seed)
    checks = [c.evaluate(outcome) for c in scenario.checks]

    return ScenarioResult(
        id=scenario.id,
        status=_status(outcome, checks),
        duration_ms=round(t.ms, 3),
        seed=scenario.seed,
        metrics=outcome.metrics,
        checks=checks,
        tags=list(scenario.tags),
        exit_code=outcome.exit_code,
        stdout=redact(outcome.stdout) if redact_output else outcome.stdout,
        stderr=redact(outcome.stderr) if redact_output else outcome.stderr,
        error=outcome.error,
        repro=repro,
        started_at=started,
    )


def run_suite(suite: Suite, *, artifacts_dir: str | Path | None = None,
              include_host: bool = False, redact_output: bool = True,
              skip_tags: frozenset[str] | set[str] = frozenset(),
              repro_dir: str | Path | None = None) -> RunReport:
    """Run every scenario in ``suite`` and return the report.

    ``skip_tags`` quarantines scenarios carrying any of those tags (SKIP, not run). ``repro_dir``, when
    set, writes a reproduction bundle for every FAIL/ERROR. ``artifacts_dir`` writes the run's
    NDJSON/JUnit/JSON.
    """
    from .repro import write_repro_bundle           # local import avoids a cycle at module load

    skip = frozenset(skip_tags)
    run_id = f"{now_iso().replace(':', '').replace('-', '')[:15]}-{uuid.uuid4().hex[:8]}"
    started = now_iso()
    with Timer() as run_timer:
        results = [_run_one(s, redact_output=redact_output, skip_tags=skip) for s in suite.scenarios]
    report = RunReport(run_id, suite.name, environment_fingerprint(include_host=include_host),
                       results, started, round(run_timer.ms, 3))
    if artifacts_dir is not None:
        write_artifacts(report, artifacts_dir)
    if repro_dir is not None:
        for r in results:
            if r.status in (Status.FAIL, Status.ERROR):
                write_repro_bundle(r, report, repro_dir)
    return report


def write_artifacts(report: RunReport, artifacts_dir: str | Path) -> dict[str, Path]:
    """Write results.ndjson, junit.xml, and report.json under ``artifacts_dir``; return their paths."""
    d = Path(artifacts_dir)
    d.mkdir(parents=True, exist_ok=True)
    paths = {
        "ndjson": d / "results.ndjson",
        "junit": d / "junit.xml",
        "report": d / "report.json",
    }
    paths["ndjson"].write_text(report.to_ndjson())
    paths["junit"].write_text(report.to_junit_xml())
    paths["report"].write_text(report.to_json())
    return paths


def exit_code(report: RunReport) -> int:
    """0 if the run is clean (no FAIL/ERROR), else 1 — the CI quality-gate signal."""
    return 0 if report.passed else 1
