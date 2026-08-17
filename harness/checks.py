"""Checks — the assertions a scenario makes about a system-under-test's output.

Each check inspects an :class:`~harness.adapters.AdapterOutcome` and returns a
:class:`~harness.schema.CheckResult`. A scenario passes only if every one of its checks passes. Keeping
checks small and composable is what lets the same output be asserted on several independent axes
(exited cleanly *and* fast enough *and* produced the expected metric).
"""

from __future__ import annotations

import operator
from typing import Callable

from .adapters import AdapterOutcome
from .schema import CheckResult

_OPS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
    "==": operator.eq, "!=": operator.ne,
}


class ExitZero:
    """The external command exited 0 (only meaningful for CommandAdapter)."""
    name = "exit_zero"

    def evaluate(self, outcome: AdapterOutcome) -> CheckResult:
        ok = outcome.exit_code == 0
        return CheckResult(self.name, ok, f"exit_code={outcome.exit_code}")


class NoError:
    """The adapter ran the SUT without an infra fault."""
    name = "no_error"

    def evaluate(self, outcome: AdapterOutcome) -> CheckResult:
        return CheckResult(self.name, outcome.ok, outcome.error or "ok")


class OutputContains:
    """stdout contains an expected substring (a log/marker the SUT should emit)."""

    def __init__(self, substring: str):
        self.substring = substring
        self.name = f"output_contains[{substring!r}]"

    def evaluate(self, outcome: AdapterOutcome) -> CheckResult:
        ok = self.substring in outcome.stdout
        return CheckResult(self.name, ok, "found" if ok else "not found in stdout")


class MetricPresent:
    """A named metric was reported at all."""

    def __init__(self, metric: str):
        self.metric = metric
        self.name = f"metric_present[{metric}]"

    def evaluate(self, outcome: AdapterOutcome) -> CheckResult:
        ok = self.metric in outcome.metrics
        return CheckResult(self.name, ok, "present" if ok else f"missing (have {sorted(outcome.metrics)})")


class MetricThreshold:
    """A reported metric satisfies ``metric <op> value`` (e.g. throughput > 1e5, latency_p99 < 50000)."""

    def __init__(self, metric: str, op: str, value: float):
        if op not in _OPS:
            raise ValueError(f"unknown operator {op!r}; use one of {sorted(_OPS)}")
        self.metric, self.op, self.value = metric, op, value
        self.name = f"metric[{metric} {op} {value}]"

    def evaluate(self, outcome: AdapterOutcome) -> CheckResult:
        if self.metric not in outcome.metrics:
            return CheckResult(self.name, False, f"metric {self.metric!r} not reported")
        actual = outcome.metrics[self.metric]
        ok = _OPS[self.op](actual, self.value)
        return CheckResult(self.name, ok, f"{self.metric}={actual} {self.op} {self.value}")
