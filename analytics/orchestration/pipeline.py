"""The ops-analytics pipeline as pure data: an ordered list of named steps, each an argv.

Keeping the *plan* separate from the *orchestrator* means the sequence is unit-testable with no
Prefect, no dbt, and no database (see test_pipeline.py). flow.py imports this and wraps each step as a
Prefect task; the nightly schedule and a local run share the exact same plan. Standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    """One pipeline step: a human name, the argv to run, and whether a non-zero exit is tolerated.

    `allow_failure` is set only for source-freshness: freshness thresholds describe a *live* OMS feed,
    so against the fixed demo/CI fixture (historical timestamps) the check reports stale by design. It
    is informative there, not a gate — so a non-zero exit must not fail the run.
    """
    name: str
    argv: tuple[str, ...]
    allow_failure: bool = False


def pipeline_steps(marts_dsn: str, *, seed: bool = False) -> list[Step]:
    """Build the ordered pipeline.

    Args:
        marts_dsn: libpq connection string for the marts Postgres, used only by the optional fixture
            load. dbt itself reads its connection from the profile/environment, not from here.
        seed: when True, prepend loading the CI/demo fixture (analytics/ci/seed_raw.sql). In production
            the OMS already populates the source tables, so this is off.

    All argv are relative to the analytics/ project directory (the flow runs from there).
    """
    steps: list[Step] = []

    if seed:
        steps.append(Step(
            "load-fixture",
            ("psql", marts_dsn, "-v", "ON_ERROR_STOP=1", "-f", "ci/seed_raw.sql"),
        ))

    steps += [
        # Transform + data-quality tests (models + generic + singular tests) in one gated command.
        Step("dbt-build", ("dbt", "build")),
        # Is the upstream OMS feed current? Report-only against the static fixture (see Step docstring).
        Step("dbt-source-freshness", ("dbt", "source", "freshness"), allow_failure=True),
        # The BI layer stays in lockstep with the marts: run every dashboard query against them.
        Step("verify-bi-spec", ("python", "metabase/verify_spec.py", "--run-sql")),
        # The dashboard-as-code still maps cleanly onto the Metabase API (no network).
        Step("provision-dry-run", ("python", "metabase/provision.py", "--dry-run")),
    ]
    return steps
