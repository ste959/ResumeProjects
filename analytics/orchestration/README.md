# Orchestration (Prefect)

The scheduling / data-orchestration leg of the analytics stack. The dbt project is the *transform*;
this runs it on a schedule as a managed pipeline with logging, retries, and clear failure semantics.

## The pipeline

One ordered flow (`ops-analytics-pipeline`), each step gated on the previous:

| Step | What it does | Gate |
|---|---|---|
| `load-fixture` *(seed only)* | Load the demo fixture into Postgres | hard |
| `dbt-build` | Run models **and** all data-quality tests | hard |
| `dbt-source-freshness` | Is the upstream OMS feed current? | report-only¹ |
| `verify-bi-spec` | Run every dashboard query against the marts | hard |
| `provision-dry-run` | Confirm the dashboard-as-code still maps to the Metabase API | hard |

¹ Freshness thresholds (`_sources.yml`) describe a **live** OMS feed (warn 12h / error 24h). Against the
fixed demo fixture (historical timestamps) it reports stale by design, so it's informative, not a gate.

## Design: plan vs. orchestrator

- [`pipeline.py`](pipeline.py) — the plan as **pure data** (an ordered list of `Step`s). No Prefect, no
  dbt, no database, so the sequence and its failure semantics are unit-tested directly
  ([`test_pipeline.py`](test_pipeline.py), run on every PR).
- [`flow.py`](flow.py) — the **Prefect** flow: wraps each step as a task (retries, per-step logging)
  and shells out. The schedule, a Prefect deployment, and a local run all share the one plan.

## Run it

**On a schedule (CI):** [`analytics-nightly.yml`](../../.github/workflows/analytics-nightly.yml) runs the
full flow nightly (and on demand via *workflow_dispatch*) against a fresh Postgres — this is where the
real Prefect execution is exercised.

**Locally** (needs Postgres + `dbt-postgres` + `prefect` + `psql`):

```bash
cd analytics
export DBT_PROFILES_DIR="$PWD"
export POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
       POSTGRES_USER=bonddesk POSTGRES_PASSWORD=bonddesk POSTGRES_DB=bonddesk
python orchestration/flow.py     # seed → build+test → freshness → verify BI
```

## Verification

- ✅ Every PR: `test_pipeline.py` (plan order, seed toggle, failure semantics) — no infra.
- ✅ Nightly: the full Prefect flow end-to-end against real Postgres.

Prefect is the orchestrator here; the plan/orchestrator split means swapping in Airflow or a plain
scheduler is a `flow.py` change, not a rewrite.
