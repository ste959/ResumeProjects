#!/usr/bin/env python3
"""Verify the dashboard spec — structure, and (when a database is reachable) that every card's SQL
actually runs against the built dbt marts and returns data.

This is the CI gate for the BI layer: it keeps the committed dashboard in lockstep with the models,
so a mart change that breaks a dashboard query fails the build instead of silently breaking a chart.
It needs no running Metabase — it exercises the same SQL Metabase would send, straight against Postgres.

Usage:
    python verify_spec.py                # structural checks only
    python verify_spec.py --run-sql      # also execute each card's SQL via psql (needs Postgres env)

Postgres connection (for --run-sql) comes from the environment, matching the analytics CI job:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

import yaml

SPEC_PATH = pathlib.Path(__file__).with_name("dashboard.yml")
VALID_DISPLAYS = {"scalar", "line", "bar", "row", "area", "pie", "table"}
GRID_WIDTH = 24

# Row counts that must hold against the committed CI fixture (analytics/ci/seed_raw.sql):
# three trade dates and three execution venues.
EXPECTED_ROWS = {"fill_rate_by_day": 3, "cycle_time_percentiles": 3, "fills_by_venue": 3}


def load_spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text())


def validate_structure(spec: dict) -> list[str]:
    errors: list[str] = []

    db = spec.get("database", {})
    for field in ("name", "engine", "schema"):
        if not db.get(field):
            errors.append(f"database.{field} is required")

    if not spec.get("dashboard", {}).get("name"):
        errors.append("dashboard.name is required")

    cards = spec.get("cards") or []
    if not cards:
        errors.append("at least one card is required")

    seen_keys: set[str] = set()
    for i, card in enumerate(cards):
        where = f"cards[{i}]"
        key = card.get("key")
        if not key:
            errors.append(f"{where}.key is required")
        elif key in seen_keys:
            errors.append(f"{where}.key '{key}' is duplicated")
        else:
            seen_keys.add(key)

        for field in ("name", "display", "sql", "layout"):
            if not card.get(field):
                errors.append(f"{where} ({key}).{field} is required")

        display = card.get("display")
        if display and display not in VALID_DISPLAYS:
            errors.append(f"{where} ({key}).display '{display}' is not one of {sorted(VALID_DISPLAYS)}")

        layout = card.get("layout") or {}
        for field in ("row", "col", "size_x", "size_y"):
            if not isinstance(layout.get(field), int):
                errors.append(f"{where} ({key}).layout.{field} must be an integer")
        if isinstance(layout.get("col"), int) and isinstance(layout.get("size_x"), int):
            if layout["col"] + layout["size_x"] > GRID_WIDTH:
                errors.append(f"{where} ({key}) overflows the {GRID_WIDTH}-column grid")

    return errors


def _psql_dsn() -> str:
    return (
        f"postgresql://{os.environ.get('POSTGRES_USER', 'bonddesk')}:"
        f"{os.environ.get('POSTGRES_PASSWORD', 'bonddesk')}@"
        f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/"
        f"{os.environ.get('POSTGRES_DB', 'bonddesk')}"
    )


def run_card_sql(spec: dict) -> list[str]:
    """Run each card's SQL against Postgres, wrapped so we get a row count. Returns error strings."""
    errors: list[str] = []
    dsn = _psql_dsn()
    for card in spec["cards"]:
        key, sql = card["key"], card["sql"].strip().rstrip(";")
        wrapped = f"select count(*) from (\n{sql}\n) _card"
        proc = subprocess.run(
            ["psql", dsn, "-tA", "-v", "ON_ERROR_STOP=1", "-c", wrapped],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            errors.append(f"card '{key}': SQL failed against marts:\n{proc.stderr.strip()}")
            continue
        rows = int(proc.stdout.strip() or "0")
        if rows == 0:
            errors.append(f"card '{key}': query returned no rows")
        expected = EXPECTED_ROWS.get(key)
        if expected is not None and rows != expected:
            errors.append(f"card '{key}': expected {expected} rows against the fixture, got {rows}")
        else:
            print(f"  ok  {key}: {rows} row(s)")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-sql", action="store_true", help="execute each card's SQL against Postgres")
    args = ap.parse_args()

    spec = load_spec()
    print(f"Validating {SPEC_PATH.name}: "
          f"{len(spec.get('cards') or [])} cards on dashboard '{spec.get('dashboard', {}).get('name')}'")

    errors = validate_structure(spec)
    if not errors and args.run_sql:
        print("Running card SQL against the marts:")
        errors += run_card_sql(spec)

    if errors:
        print("\nSPEC VERIFICATION FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("Dashboard spec OK" + (" (structure + live SQL)" if args.run_sql else " (structure)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
