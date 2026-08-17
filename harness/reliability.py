"""Determinism / flakiness gate — the reliability heart.

A trustworthy validation suite must itself be reliable: a scenario should give the *same* verdict every
time it runs. This module runs each scenario several times under its fixed seed and classifies it:

* **stable_pass** — passed every time (as it should).
* **stable_fail** — failed every time. That's a *real, reproducible* defect in the system under test —
  not flakiness — and the normal suite already catches it.
* **flaky** — the verdict changed between runs. This is the enemy: a flaky test erodes trust in the
  whole suite, so it should be quarantined and fixed rather than left to fail intermittently in CI.
* **skipped** — precondition never met (e.g. the device isn't present).

It also reports which *metrics* varied in value across runs — useful signal (a timing metric varying is
expected; a computed result varying is a determinism bug), surfaced without failing the gate on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .runner import _run_one
from .scenario import Scenario, Suite
from .schema import Status


@dataclass
class DeterminismResult:
    scenario_id: str
    repeats: int
    statuses: list[str]                              # per-run status values
    pass_count: int
    classification: str                              # stable_pass | stable_fail | flaky | skipped
    varying_metrics: list[str] = field(default_factory=list)

    @property
    def is_flaky(self) -> bool:
        return self.classification == "flaky"

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_id, "repeats": self.repeats, "statuses": self.statuses,
            "pass_count": self.pass_count, "classification": self.classification,
            "varying_metrics": self.varying_metrics,
        }


def _varying_metrics(metric_dicts: list[dict]) -> list[str]:
    keys: set[str] = set().union(*[set(d) for d in metric_dicts]) if metric_dicts else set()
    varying = []
    for k in sorted(keys):
        values = [d.get(k, None) for d in metric_dicts]
        if len({repr(v) for v in values}) != 1:      # repr keys handles floats/None uniformly
            varying.append(k)
    return varying


def _classify(statuses: list[Status]) -> tuple[str, int]:
    pass_count = sum(s is Status.PASS for s in statuses)
    skip_count = sum(s is Status.SKIP for s in statuses)
    n = len(statuses)
    if skip_count == n:
        return "skipped", pass_count
    if pass_count == n:
        return "stable_pass", pass_count
    # Flaky = the verdict was not the same every run. Judge on the distinct non-skip verdicts, so a run
    # that alternates FAIL and ERROR (sometimes the SUT fails a check, sometimes the adapter crashes) is
    # correctly flaky — not collapsed into stable_fail and waved through the gate.
    distinct = {s for s in statuses if s is not Status.SKIP}
    if len(distinct) == 1:
        return "stable_fail", pass_count             # a single, uniform failing verdict
    return "flaky", pass_count


def check_determinism(scenario: Scenario, *, repeats: int = 5,
                      redact_output: bool = True) -> DeterminismResult:
    """Run ``scenario`` ``repeats`` times under its seed and classify its verdict stability."""
    if repeats < 2:
        raise ValueError("determinism needs at least 2 repeats")
    results = [_run_one(scenario, redact_output=redact_output) for _ in range(repeats)]
    statuses = [r.status for r in results]
    classification, pass_count = _classify(statuses)
    return DeterminismResult(
        scenario_id=scenario.id,
        repeats=repeats,
        statuses=[s.value for s in statuses],
        pass_count=pass_count,
        classification=classification,
        varying_metrics=_varying_metrics([r.metrics for r in results]),
    )


def flakiness_report(suite: Suite, *, repeats: int = 5, redact_output: bool = True,
                     skip_tags: frozenset[str] | set[str] = frozenset()) -> list[DeterminismResult]:
    """Probe every (non-quarantined) scenario for verdict stability."""
    skip = frozenset(skip_tags)
    return [check_determinism(s, repeats=repeats, redact_output=redact_output)
            for s in suite.scenarios if not skip.intersection(s.tags)]


def gate_passes(reports: list[DeterminismResult]) -> bool:
    """The gate fails if any scenario is flaky. (stable_fail is a real defect for the normal suite to
    report; skipped and stable_pass are fine.)"""
    return not any(r.is_flaky for r in reports)
