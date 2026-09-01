"""Prefect flow that orchestrates the ops-analytics pipeline.

This is the orchestration layer over the dbt project: it runs the pipeline as a Prefect flow with
per-step logging, retries, and clear failure semantics, so the same run works on a schedule (the
nightly GitHub Actions workflow), in a Prefect deployment, or locally. The *plan* lives in pipeline.py
(pure, unit-tested); this module only wraps each step in Prefect and shells out.

Run locally (needs a reachable Postgres, dbt-postgres, and — for the fixture — psql):

    cd analytics
    export DBT_PROFILES_DIR="$PWD"
    export POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
           POSTGRES_USER=bonddesk POSTGRES_PASSWORD=bonddesk POSTGRES_DB=bonddesk
    python orchestration/flow.py            # loads the fixture, then runs the pipeline
"""
from __future__ import annotations

import os
import pathlib
import subprocess

from prefect import flow, get_run_logger, task

from pipeline import Step, pipeline_steps

# The flow runs from the analytics/ project directory so dbt and the relative argv resolve.
ANALYTICS_DIR = pathlib.Path(__file__).resolve().parent.parent


def _marts_dsn() -> str:
    return (
        f"postgresql://{os.environ.get('POSTGRES_USER', 'bonddesk')}:"
        f"{os.environ.get('POSTGRES_PASSWORD', 'bonddesk')}@"
        f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/"
        f"{os.environ.get('POSTGRES_DB', 'bonddesk')}"
    )


@task(retries=2, retry_delay_seconds=10)
def run_step(step: Step) -> None:
    logger = get_run_logger()
    logger.info("→ %s: %s", step.name, " ".join(step.argv))
    proc = subprocess.run(step.argv, cwd=ANALYTICS_DIR, capture_output=True, text=True)
    if proc.stdout:
        logger.info(proc.stdout.strip())
    if proc.returncode != 0:
        if step.allow_failure:
            logger.warning("%s exited %d (tolerated): %s", step.name, proc.returncode, proc.stderr.strip())
            return
        logger.error(proc.stderr.strip())
        raise RuntimeError(f"step '{step.name}' failed with exit code {proc.returncode}")


@flow(name="ops-analytics-pipeline")
def ops_analytics_pipeline(seed: bool = True) -> None:
    """Refresh the analytics marts and verify the layer end-to-end.

    Steps run strictly in order — each waits for the previous to succeed — because every stage depends
    on the one before it (build → freshness → BI verification).
    """
    logger = get_run_logger()
    steps = pipeline_steps(_marts_dsn(), seed=seed)
    logger.info("Running %d pipeline steps (seed=%s)", len(steps), seed)
    for step in steps:
        run_step(step)
    logger.info("ops-analytics pipeline complete.")


if __name__ == "__main__":
    ops_analytics_pipeline()
