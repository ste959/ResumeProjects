"""Command-line entry point:  ``python -m harness [--suite mod:attr] [--out DIR] [--tag TAG]``.

Loads a suite, runs it, prints a summary table, writes artifacts, and exits non-zero if anything
failed or errored — so the same command doubles as a CI quality gate.
"""

from __future__ import annotations

import argparse
import importlib

from .runner import exit_code, run_suite
from .scenario import Suite
from .schema import Status

_GLYPH = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.ERROR: "ERR ", Status.SKIP: "skip"}


def _load_suite(ref: str) -> Suite:
    module_name, _, attr = ref.partition(":")
    module = importlib.import_module(module_name)
    suite = getattr(module, attr or "SUITE")
    if not isinstance(suite, Suite):
        raise SystemExit(f"{ref} is not a Suite")
    return suite


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness", description="Run a validation suite.")
    ap.add_argument("--suite", default="harness.suites.example:SUITE",
                    help="suite reference as module:attr (default: the example suite)")
    ap.add_argument("--out", default=None, help="directory for results.ndjson / junit.xml / report.json")
    ap.add_argument("--tag", default=None, help="only run scenarios carrying this tag")
    ap.add_argument("--include-host", action="store_true", help="record hostname in the fingerprint")
    args = ap.parse_args(argv)

    suite = _load_suite(args.suite)
    if args.tag:
        suite = suite.select(args.tag)

    report = run_suite(suite, artifacts_dir=args.out, include_host=args.include_host)

    print(f"\nsuite: {report.suite}   run: {report.run_id}   "
          f"env: {report.environment['os']}/{report.environment['arch']} "
          f"py{report.environment['python']} @ {report.environment.get('git_commit')}\n")
    width = max((len(r.id) for r in report.results), default=10)
    for r in report.results:
        metrics = "  ".join(f"{k}={_fmt(v)}" for k, v in list(r.metrics.items())[:3])
        note = r.error if r.status in (Status.SKIP, Status.ERROR) and r.error else metrics
        print(f"  [{_GLYPH[r.status]}] {r.id:<{width}}  {r.duration_ms:7.1f}ms   {note}")

    c = report.counts()
    print(f"\n{c['PASS']} passed, {c['FAIL']} failed, {c['ERROR']} errored, {c['SKIP']} skipped "
          f"in {report.duration_ms:.0f}ms")
    if args.out:
        print(f"artifacts → {args.out}/  (results.ndjson, junit.xml, report.json)")
    return exit_code(report)


def _fmt(v) -> str:
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


if __name__ == "__main__":
    raise SystemExit(main())
