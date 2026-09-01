# Self-service BI (Metabase) over the dbt marts

The [Slice 1](../README.md) marts are the modeled, tested data; this is the **stakeholder-facing front
door**. Metabase reads the `analytics` marts straight from Postgres and serves the
**Desk Operations — Fill Performance** dashboard to people who don't write SQL.

The dashboard is **code**, not clicks. Everything — the data-source connection, the six cards, and the
layout — is declared in [`dashboard.yml`](dashboard.yml) and applied through the Metabase API by
[`provision.py`](provision.py). That means it is version-controlled, reviewed in PRs, reproducible on a
fresh container, and gated in CI (a mart change that breaks a card fails the build).

## The dashboard

| Card | What it answers | Model |
|---|---|---|
| Notional filled (total) | How much got done | `fct_fills` |
| Reject rate (all days) | Order-quality signal | `kpi_fill_performance_daily` |
| Daily fill rate | Throughput quality over time | `kpi_fill_performance_daily` |
| Order → fill cycle time (p50 / p95) | How fast we fill | `kpi_fill_performance_daily` |
| Order outcomes by day | Filled / partial / rejected / cancelled mix | `kpi_fill_performance_daily` |
| Execution by venue | Venue scorecard (fills & notional) | `fct_fills` |

## Bring it up (local)

Metabase runs on **http://localhost:3001** (Grafana already holds 3000).

```bash
# 1. Start Postgres + Metabase
docker compose up -d postgres metabase

# 2. Build the marts into that Postgres (see ../README.md). For a self-contained demo, load the
#    fixture first, then run dbt:
psql "postgresql://bonddesk:bonddesk@localhost:5432/bonddesk" -v ON_ERROR_STOP=1 -f ../ci/seed_raw.sql
( cd .. && DBT_PROFILES_DIR="$PWD" dbt build )

# 3. Provision the dashboard as code (idempotent). Metabase reaches Postgres as the compose service
#    name, so point MARTS_HOST at it:
MARTS_HOST=postgres python provision.py

# 4. Open http://localhost:3001 → dashboard "Desk Operations — Fill Performance".
```

`provision.py` is safe to re-run: it matches the data source, cards, and dashboard by name and reuses
them. Preview exactly what it would send without a running Metabase:

```bash
python provision.py --dry-run
```

## How it's verified

| Part | How | Where |
|---|---|---|
| Spec is well-formed | `verify_spec.py` (structure) | CI + locally |
| Every card's SQL runs against the marts and returns the expected rows | `verify_spec.py --run-sql` | CI (`analytics` job, against the built marts) |
| The spec → Metabase API payload mapping | `provision.py --dry-run` | CI + locally |
| The live API calls | run `provision.py` against a booted Metabase | local (not booted in CI) |

The live provisioning is the one part CI does not exercise — booting Metabase per run is slow and
flaky, so it is a documented local step. Everything that can be checked without a running Metabase is.

## Configuration

`provision.py` reads all connection details and credentials from the environment (never committed):
`MB_URL`, `MB_ADMIN_EMAIL`, `MB_ADMIN_PASSWORD`, and `MARTS_HOST/PORT/DB/USER/PASSWORD`. The defaults
target the docker-compose stack for a zero-config demo; **change `MB_ADMIN_PASSWORD` for anything real.**
Pinned to Metabase OSS `v0.59.31` (see `docker-compose.yml`).
