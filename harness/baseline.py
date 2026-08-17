"""Quality gates — golden baselines and performance-regression thresholds.

Capture a run as a **baseline** (the golden result), then compare a later run against it and fail if
something regressed. Three kinds of regression, judged differently:

* **Status** — a scenario that passed in the baseline now fails. Always gated; hardware-independent.
* **Accuracy** (`exact` rule) — a deterministic metric drifted beyond an absolute tolerance. Gated
  regardless of machine, because a seeded computation must reproduce everywhere.
* **Performance** (`higher`/`lower` rule) — a throughput/latency metric moved the wrong way beyond a
  relative tolerance. Gated **only on comparable hardware** — a perf baseline captured on one CPU can't
  fairly judge a run on another, so across a hardware mismatch these are reported as *drift notes*, not
  gating regressions.

That last rule is the honest core of "comparable results across a hardware ecosystem": status and
accuracy are portable, raw performance is not, and the gate reflects the difference instead of
pretending otherwise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .schema import RunReport, Status
from .telemetry import now_iso

BASELINE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MetricRule:
    """How to judge a metric. ``direction``: 'higher' / 'lower' (perf, relative ``tol``) or 'exact'
    (accuracy, absolute ``tol``)."""
    direction: str
    tol: float

    def __post_init__(self):
        if self.direction not in ("higher", "lower", "exact"):
            raise ValueError(f"direction must be higher|lower|exact, got {self.direction!r}")

    @property
    def hardware_sensitive(self) -> bool:
        return self.direction in ("higher", "lower")

    def regressed(self, baseline: float, current: float) -> bool:
        if self.direction == "higher":
            return current < baseline * (1.0 - self.tol)
        if self.direction == "lower":
            return current > baseline * (1.0 + self.tol)
        return abs(current - baseline) > self.tol            # exact


@dataclass
class BaselinePolicy:
    """Per-metric rules. Metrics without a rule are reported as drift but never gate."""
    rules: dict[str, MetricRule] = field(default_factory=dict)

    def rule(self, metric: str) -> MetricRule | None:
        return self.rules.get(metric)


@dataclass
class Baseline:
    suite: str
    environment: dict
    scenarios: dict[str, dict]                                # id -> {"status": str, "metrics": {...}}
    captured_at: str = ""
    schema_version: int = BASELINE_SCHEMA_VERSION

    def to_json(self) -> str:
        return json.dumps({
            "suite": self.suite, "schema_version": self.schema_version,
            "captured_at": self.captured_at, "environment": self.environment,
            "scenarios": self.scenarios,
        }, indent=2, default=str)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Baseline":
        d = json.loads(Path(path).read_text())
        return cls(d["suite"], d["environment"], d["scenarios"],
                   d.get("captured_at", ""), d.get("schema_version", BASELINE_SCHEMA_VERSION))


def capture_baseline(report: RunReport) -> Baseline:
    """Snapshot a run as the golden baseline (per-scenario status + metrics)."""
    scenarios = {r.id: {"status": r.status.value, "metrics": dict(r.metrics)} for r in report.results}
    return Baseline(report.suite, report.environment, scenarios, now_iso())


@dataclass(frozen=True)
class Regression:
    scenario: str
    kind: str                                                # status | accuracy | performance | missing
    detail: str
    metric: str | None = None


@dataclass
class Comparison:
    regressions: list[Regression] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)           # non-gating: perf drift on other HW, new scenarios
    hardware_comparable: bool = True

    @property
    def passed(self) -> bool:
        return not self.regressions


def _comparable(a: dict, b: dict) -> bool:
    return a.get("os") == b.get("os") and a.get("arch") == b.get("arch")


def compare_to_baseline(report: RunReport, baseline: Baseline,
                        policy: BaselinePolicy | None = None) -> Comparison:
    """Compare ``report`` against ``baseline`` under ``policy``; collect gating regressions + notes."""
    policy = policy or BaselinePolicy()
    hw_ok = _comparable(report.environment, baseline.environment)
    cmp = Comparison(hardware_comparable=hw_ok)
    if not hw_ok:
        cmp.notes.append(f"hardware differs from baseline "
                         f"({baseline.environment.get('os')}/{baseline.environment.get('arch')} → "
                         f"{report.environment.get('os')}/{report.environment.get('arch')}); "
                         f"performance regressions are downgraded to drift notes.")

    current = {r.id: r for r in report.results}
    for sid, base in baseline.scenarios.items():
        if sid not in current:
            cmp.notes.append(f"{sid}: in baseline but not in this run (scenario removed?)")
            continue
        result = current[sid]

        # Status regression: was PASS, now failing.
        if base["status"] == Status.PASS.value and result.status in (Status.FAIL, Status.ERROR):
            cmp.regressions.append(Regression(sid, "status",
                                              f"was PASS, now {result.status.value}"))
        elif base["status"] == Status.PASS.value and result.status is Status.SKIP:
            cmp.notes.append(f"{sid}: was PASS, now SKIP (no longer run)")

        # Metric regressions, per policy rule.
        for metric, base_val in base.get("metrics", {}).items():
            rule = policy.rule(metric)
            if rule is None or not isinstance(base_val, (int, float)):
                continue
            if metric not in result.metrics:
                cmp.regressions.append(Regression(sid, "missing", f"metric {metric!r} no longer reported", metric))
                continue
            cur_val = result.metrics[metric]
            if not isinstance(cur_val, (int, float)) or not rule.regressed(base_val, cur_val):
                continue
            detail = f"{metric}: {base_val} → {cur_val} ({rule.direction}, tol {rule.tol})"
            if rule.hardware_sensitive and not hw_ok:
                cmp.notes.append(f"{sid}: perf drift {detail}")     # not gated across hardware
            else:
                kind = "performance" if rule.hardware_sensitive else "accuracy"
                cmp.regressions.append(Regression(sid, kind, detail, metric))

    for sid in current:
        if sid not in baseline.scenarios:
            cmp.notes.append(f"{sid}: new scenario (not in baseline)")
    return cmp
