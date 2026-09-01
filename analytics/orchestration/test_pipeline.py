"""Unit tests for the pure pipeline planner. No Prefect, no dbt, no database — just the plan.

Run: `python -m pytest analytics/orchestration/test_pipeline.py -q`
"""
from __future__ import annotations

from pipeline import Step, pipeline_steps

DSN = "postgresql://u:p@h:5432/db"


def test_default_plan_has_no_seed_and_expected_order():
    steps = pipeline_steps(DSN)  # seed defaults to False (production: OMS already populated)
    names = [s.name for s in steps]
    assert names == [
        "dbt-build",
        "dbt-source-freshness",
        "verify-bi-spec",
        "provision-dry-run",
    ]


def test_seed_prepends_fixture_load():
    steps = pipeline_steps(DSN, seed=True)
    assert steps[0].name == "load-fixture"
    assert steps[0].argv == ("psql", DSN, "-v", "ON_ERROR_STOP=1", "-f", "ci/seed_raw.sql")
    # The rest of the plan is unchanged and still in order.
    assert [s.name for s in steps[1:]] == [s.name for s in pipeline_steps(DSN)]


def test_only_freshness_tolerates_failure():
    # Freshness is report-only against a static fixture; everything else is a hard gate.
    for s in pipeline_steps(DSN, seed=True):
        assert s.allow_failure == (s.name == "dbt-source-freshness")


def test_build_runs_models_and_tests_together():
    steps = {s.name: s for s in pipeline_steps(DSN)}
    assert steps["dbt-build"].argv == ("dbt", "build")  # `build` = run + test in one gated command


def test_steps_are_immutable():
    step = pipeline_steps(DSN)[0]
    assert isinstance(step, Step)
    try:
        step.name = "mutated"  # frozen dataclass
    except Exception:
        return
    raise AssertionError("Step should be immutable")
