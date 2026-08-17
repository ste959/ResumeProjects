"""Reproduction bundles — everything needed to investigate and re-run a failing scenario.

When a scenario FAILs or ERRORs, the harness can write a self-contained bundle capturing the seed, the
configuration, the environment it ran in, the (redacted) captured logs, exactly which checks failed,
and the precise command to reproduce it. That is the difference between "a test went red in CI" and
"here is the seed, the machine, the logs, and the one line that reproduces it" — the diagnostic
collateral a lab needs to turn a failure into a fix.

Bundles contain only already-redacted output, so they are safe to attach to a ticket or share.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import RunReport, ScenarioResult


def _rerun_instructions(result: ScenarioResult) -> str:
    lines = [
        f"# Reproduce scenario '{result.id}'  (status: {result.status.value}, seed: {result.seed})",
        "",
        "The system under test was invoked as:",
        f"    {result.repro or '(no reproduction descriptor available)'}",
        "",
        "Via the harness (re-runs this scenario deterministically under the same seed):",
        f"    python -m harness --tag {result.id}     # if the scenario carries a matching tag",
        "",
        "Failed checks:" if result.status.value == "FAIL" else "Error:",
    ]
    if result.status.value == "FAIL":
        for c in result.checks:
            if not c.ok:
                lines.append(f"    - {c.name}: {c.detail}")
    else:
        lines.append(f"    {result.error}")
    return "\n".join(lines) + "\n"


def write_repro_bundle(result: ScenarioResult, report: RunReport, out_dir: str | Path) -> Path:
    """Write a reproduction bundle for ``result`` under ``out_dir/<run_id>/<scenario_id>/``.

    Returns the bundle directory. Contents:
      * ``bundle.json`` — structured: seed, tags, checks, error, metrics, environment, repro command;
      * ``stdout.log`` / ``stderr.log`` — the captured (already-redacted) output;
      * ``REPRODUCE.txt`` — human-readable re-run instructions.
    """
    bundle_dir = Path(out_dir) / report.run_id / result.id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": report.run_id,
        "suite": report.suite,
        "scenario": result.id,
        "status": result.status.value,
        "seed": result.seed,
        "tags": result.tags,
        "exit_code": result.exit_code,
        "error": result.error,
        "metrics": result.metrics,
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in result.checks],
        "repro_command": result.repro,
        "environment": report.environment,
        "started_at": result.started_at,
        "schema_version": report.schema_version,
    }
    (bundle_dir / "bundle.json").write_text(json.dumps(manifest, indent=2, default=str))
    (bundle_dir / "stdout.log").write_text(result.stdout)
    (bundle_dir / "stderr.log").write_text(result.stderr)
    (bundle_dir / "REPRODUCE.txt").write_text(_rerun_instructions(result))
    return bundle_dir
