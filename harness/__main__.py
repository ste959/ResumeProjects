"""Command-line entry point:  ``python -m harness [--suite mod:attr] [--out DIR] [--tag TAG]``.

Loads a suite, runs it, prints a summary table, writes artifacts, and exits non-zero if anything
failed or errored — so the same command doubles as a CI quality gate.
"""

from __future__ import annotations

import argparse
import importlib

from .reliability import flakiness_report, gate_passes
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
    ap.add_argument("--repro-dir", default=None, help="write a reproduction bundle for each FAIL/ERROR")
    ap.add_argument("--quarantine", action="append", default=[], metavar="TAG",
                    help="skip scenarios carrying this tag (repeatable)")
    ap.add_argument("--check-determinism", action="store_true",
                    help="run each scenario N times and gate on flakiness instead of a single run")
    ap.add_argument("--repeats", type=int, default=5, help="repeats for --check-determinism (default 5)")
    args = ap.parse_args(argv)

    suite = _load_suite(args.suite)
    if args.tag:
        suite = suite.select(args.tag)

    if args.check_determinism:
        return _determinism_gate(suite, args.repeats, frozenset(args.quarantine))

    report = run_suite(suite, artifacts_dir=args.out, include_host=args.include_host,
                       skip_tags=frozenset(args.quarantine), repro_dir=args.repro_dir)

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
    if args.repro_dir and (c["FAIL"] or c["ERROR"]):
        print(f"repro bundles → {args.repro_dir}/{report.run_id}/")
    return exit_code(report)


def _determinism_gate(suite: Suite, repeats: int, quarantine: frozenset[str]) -> int:
    """Run the flakiness gate: each scenario N times, fail if any verdict is unstable."""
    reports = flakiness_report(suite, repeats=repeats, skip_tags=quarantine)
    print(f"\ndeterminism gate: {len(reports)} scenarios × {repeats} runs\n")
    width = max((len(r.scenario_id) for r in reports), default=10)
    for r in reports:
        varying = f"  varying metrics: {', '.join(r.varying_metrics)}" if r.varying_metrics else ""
        print(f"  {r.classification:<12} {r.scenario_id:<{width}}  "
              f"{r.pass_count}/{r.repeats} passed{varying}")
    flaky = [r.scenario_id for r in reports if r.is_flaky]
    ok = gate_passes(reports)
    print(f"\n{'PASS' if ok else 'FAIL'}: "
          f"{'no flaky scenarios' if ok else 'flaky: ' + ', '.join(flaky)}")
    return 0 if ok else 1


def _fmt(v) -> str:
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


if __name__ == "__main__":
    raise SystemExit(main())
