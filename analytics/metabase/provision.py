#!/usr/bin/env python3
"""Provision the Metabase "Desk Operations — Fill Performance" dashboard from dashboard.yml.

Dashboard-as-code: instead of clicking the dashboard together in the UI (and losing it on the next
container rebuild), the whole thing — data-source connection, cards, and layout — is declared in
dashboard.yml and applied here through the Metabase REST API. Re-running is idempotent: existing
objects are matched by name and reused, so this is safe to run repeatedly.

Targets the Metabase OSS API pinned in docker-compose.yml (v0.59.x). Standard library only.

Verification note: the live API calls need a running Metabase, which is not booted in CI or in the
dev sandbox — so the HTTP path here is believed-correct against v0.59, not locally verified. What *is*
verified in CI (verify_spec.py) is the spec and that every card's SQL runs against the marts, plus
`--dry-run` below, which builds every API payload with no network. Run it live locally to confirm.

Environment:
    MB_URL            Metabase base URL           (default http://localhost:3001)
    MB_ADMIN_EMAIL    admin email                 (default admin@bonddesk.local)
    MB_ADMIN_PASSWORD admin password              (default: see below; demo only — change it)
    MARTS_HOST/PORT/DB/USER/PASSWORD  Postgres connection Metabase should use for the marts
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

import yaml

SPEC_PATH = pathlib.Path(__file__).with_name("dashboard.yml")

MB_URL = os.environ.get("MB_URL", "http://localhost:3001").rstrip("/")
ADMIN_EMAIL = os.environ.get("MB_ADMIN_EMAIL", "admin@bonddesk.local")
# Demo default so `docker compose up` + this script "just works"; override in any real deployment.
ADMIN_PASSWORD = os.environ.get("MB_ADMIN_PASSWORD", "MetabaseDemo123")


def marts_details() -> dict:
    """Postgres connection details Metabase will use to read the dbt marts."""
    return {
        "host": os.environ.get("MARTS_HOST", "postgres"),   # the docker-compose service name
        "port": int(os.environ.get("MARTS_PORT", "5432")),
        "dbname": os.environ.get("MARTS_DB", "bonddesk"),
        "user": os.environ.get("MARTS_USER", "bonddesk"),
        "password": os.environ.get("MARTS_PASSWORD", "bonddesk"),
        "schema-filters-type": "all",
        "ssl": False,
        "tunnel-enabled": False,
    }


# ── API payload builders (pure; exercised by --dry-run) ──────────────────────────────────────────

def build_database_payload(spec: dict) -> dict:
    db = spec["database"]
    return {"name": db["name"], "engine": db["engine"], "details": marts_details()}


def build_card_payload(card: dict, database_id) -> dict:
    return {
        "name": card["name"],
        "display": card["display"],
        "visualization_settings": {},
        "dataset_query": {
            "type": "native",
            "native": {"query": card["sql"].strip(), "template-tags": {}},
            "database": database_id,
        },
    }


def build_dashcards_payload(spec: dict, card_ids: dict) -> list[dict]:
    """One dashcard per card; negative ids tell Metabase these are new placements."""
    dashcards = []
    for i, card in enumerate(spec["cards"]):
        lay = card["layout"]
        dashcards.append({
            "id": -(i + 1),
            "card_id": card_ids[card["key"]],
            "row": lay["row"], "col": lay["col"],
            "size_x": lay["size_x"], "size_y": lay["size_y"],
        })
    return dashcards


# ── HTTP plumbing ────────────────────────────────────────────────────────────────────────────────

def _request(method: str, path: str, body: dict | None, session: str | None) -> object:
    url = f"{MB_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("X-Metabase-Session", session)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Metabase API {method} {path} failed: {e.code} {e.read().decode()[:500]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Cannot reach Metabase at {MB_URL} ({e.reason}). Is the container up?")


def _as_list(result: object) -> list:
    """GET collection endpoints return either a bare list or {'data': [...]} across versions."""
    if isinstance(result, dict):
        return result.get("data", [])
    return result or []


# ── Idempotent operations ────────────────────────────────────────────────────────────────────────

def setup_or_login() -> str:
    props = _request("GET", "/api/session/properties", None, None)
    token = props.get("setup-token") if isinstance(props, dict) else None
    if token:
        print("First-run setup: creating the admin user.")
        res = _request("POST", "/api/setup", {
            "token": token,
            "prefs": {"site_name": "BondDesk Ops", "allow_tracking": False},
            "user": {
                "first_name": "Ops", "last_name": "Admin",
                "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "site_name": "BondDesk Ops",
            },
        }, None)
        return res["id"]
    print("Metabase already initialized: logging in.")
    res = _request("POST", "/api/session", {"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, None)
    return res["id"]


def ensure_database(spec: dict, session: str):
    payload = build_database_payload(spec)
    for db in _as_list(_request("GET", "/api/database", None, session)):
        if db.get("name") == payload["name"]:
            print(f"Data source '{payload['name']}' already present (id={db['id']}).")
            return db["id"]
    created = _request("POST", "/api/database", payload, session)
    print(f"Created data source '{payload['name']}' (id={created['id']}).")
    return created["id"]


def ensure_card(card: dict, database_id, session: str):
    payload = build_card_payload(card, database_id)
    for existing in _as_list(_request("GET", "/api/card", None, session)):
        if existing.get("name") == payload["name"]:
            return existing["id"]
    created = _request("POST", "/api/card", payload, session)
    print(f"Created card '{payload['name']}' (id={created['id']}).")
    return created["id"]


def ensure_dashboard(spec: dict, session: str):
    name = spec["dashboard"]["name"]
    for dash in _as_list(_request("GET", "/api/dashboard", None, session)):
        if dash.get("name") == name:
            print(f"Dashboard '{name}' already present (id={dash['id']}).")
            return dash["id"]
    created = _request("POST", "/api/dashboard",
                       {"name": name, "description": spec["dashboard"].get("description", "")}, session)
    print(f"Created dashboard '{name}' (id={created['id']}).")
    return created["id"]


def provision(spec: dict) -> None:
    session = setup_or_login()
    database_id = ensure_database(spec, session)
    card_ids = {card["key"]: ensure_card(card, database_id, session) for card in spec["cards"]}
    dashboard_id = ensure_dashboard(spec, session)
    _request("PUT", f"/api/dashboard/{dashboard_id}",
             {"dashcards": build_dashcards_payload(spec, card_ids)}, session)
    print(f"\nDone. Open {MB_URL} → dashboard '{spec['dashboard']['name']}'.")


def dry_run(spec: dict) -> None:
    """Build every payload with no network, so the spec→API mapping is exercised in CI."""
    placeholder_ids = {card["key"]: f"<{card['key']}>" for card in spec["cards"]}
    print("=== database ===");  print(json.dumps(build_database_payload(spec), indent=2))
    print("=== cards ===")
    for card in spec["cards"]:
        print(json.dumps(build_card_payload(card, "<db-id>"), indent=2))
    print("=== dashcards ===")
    print(json.dumps(build_dashcards_payload(spec, placeholder_ids), indent=2))
    print(f"\nDry run OK: {len(spec['cards'])} cards for dashboard '{spec['dashboard']['name']}'.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print all API payloads without contacting Metabase")
    args = ap.parse_args()
    spec = yaml.safe_load(SPEC_PATH.read_text())
    if args.dry_run:
        dry_run(spec)
    else:
        provision(spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
