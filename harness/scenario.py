"""Scenario and Suite — the declarative unit of validation collateral.

A :class:`Scenario` binds a system-under-test (via its adapter) to the checks that must hold and the
seed it runs under; a :class:`Suite` is an ordered, named collection of them. This is the "packaged
test collateral" a lab ships: data, not imperative scripts, so scenarios can be listed, filtered,
counted for coverage, and run identically everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

from .adapters import AdapterOutcome
from .schema import CheckResult


class Adapter(Protocol):
    def run(self, seed: int) -> AdapterOutcome: ...


class Check(Protocol):
    name: str
    def evaluate(self, outcome: AdapterOutcome) -> CheckResult: ...


@dataclass
class Scenario:
    """One validation scenario: drive ``adapter`` under ``seed`` and assert every check holds."""
    id: str
    adapter: Adapter
    checks: list[Check] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    seed: int = 0
    # Optional precondition; if it returns a reason string the scenario is SKIPped (e.g. "no JDK").
    skip_if: Callable[[], str | None] | None = None


@dataclass
class Suite:
    name: str
    scenarios: list[Scenario] = field(default_factory=list)

    def select(self, tag: str) -> "Suite":
        """A sub-suite of the scenarios carrying ``tag`` — for running a slice of the collateral."""
        return Suite(f"{self.name}:{tag}", [s for s in self.scenarios if tag in s.tags])

    def __len__(self) -> int:
        return len(self.scenarios)
