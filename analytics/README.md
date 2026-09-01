# BondDesk Ops Analytics (dbt)

A small **analytics-engineering** layer that turns the OMS's operational tables into a tested,
dimensional model and a standardized KPI table — the pattern a data & operations team runs to feed
dashboards and executives:

```
OMS Postgres (orders, executions, security)   ← owned by the app (Flyway), dbt only reads it
        │  sources
        ▼
   staging  (stg_orders, stg_executions, stg_securities)   views: rename + normalize
        │  ref()
        ▼
    marts   dim_security · dim_venue · fct_fills   tables: dimensional model
        │
        ▼
    KPIs    kpi_fill_performance_daily            throughput · fill/reject rate · cycle-time p50/p95
```

Every model and its lineage are versioned; every load is **tested** (generic tests + two singular
data-quality checks) and gated in CI. Nothing is hand-run and eyeballed.

## What's here

| Layer | Models | Notes |
|---|---|---|
| **Sources** | `oms.orders`, `oms.execution`, `oms.security` | The live OMS tables (`models/staging/_sources.yml`). |
| **Staging** | `stg_orders`, `stg_executions`, `stg_securities` | Thin views: rename, normalize enum casing. |
| **Marts** | `fct_fills` (grain: one fill), `dim_security`, `dim_venue` | Star schema; `fct_fills` carries `cycle_time_seconds`. |
| **KPIs** | `kpi_fill_performance_daily` | Daily fill rate, reject rate, and order-to-fill cycle-time percentiles (`percentile_cont`). |

## Data quality

- **Generic tests** (`_staging.yml`, `_marts.yml`): `not_null`, `unique`, `relationships`
  (referential integrity across staging → marts), `accepted_values` on order status.
- **Singular tests** (`tests/`):
  - `assert_fills_reconcile_to_orders.sql` — every order's fills sum to its `filled_quantity` and
    never exceed the ordered quantity (a reconciliation check between the two operational tables).
  - `assert_non_negative_cycle_time.sql` — a fill cannot precede its order.

`dbt build` runs the models **and** these tests as one gated step; a failure fails CI.

## Run it

Needs a reachable Postgres. The CI job (`.github/workflows/ci.yml`, job **Analytics (dbt)**) stands one
up, loads a fixture, and runs the full build — so this is verified on every push/PR.

Locally:

```bash
cd analytics
export DBT_PROFILES_DIR="$PWD"
# point at your Postgres (defaults shown):
export POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
       POSTGRES_USER=bonddesk POSTGRES_PASSWORD=bonddesk POSTGRES_DB=bonddesk

# CI/demo only: load the fixture that stands in for the live OMS tables
psql "postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB" \
     -v ON_ERROR_STOP=1 -f ci/seed_raw.sql

dbt build     # runs models + all data-quality tests
dbt docs generate && dbt docs serve   # optional: browse lineage
```

Against a real OMS database, skip the fixture and point the source at the live schema — the models are
unchanged.

## Self-service BI (Metabase)

A [Metabase](metabase/README.md) service (docker-compose, `:3001`) reads these marts and serves the
**Desk Operations — Fill Performance** dashboard to non-technical stakeholders. The dashboard is
**declared as code** (`metabase/dashboard.yml`) and applied via the Metabase API
(`metabase/provision.py`) — version-controlled, not clicked together. CI validates the spec and runs
every dashboard query against the built marts, so the BI layer can't silently drift from the models.

## Roadmap

- **Slice 3:** orchestration (a Prefect flow / scheduled Actions run) + source-freshness and
  reconciliation checks on a schedule.
