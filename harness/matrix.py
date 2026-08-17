"""Configuration-matrix orchestration — run the same suite across many configurations and compare.

A readiness lab runs one packaged suite across a matrix of configurations (the OEM / silicon / driver /
power-profile analog) and needs *comparable* results: same scenarios, same seeds, only the configuration
varies. This module runs the suite once per named configuration and aggregates the runs into a grid,
whose most valuable output is the set of **config-dependent failures** — scenarios that pass under some
configurations and fail under others. Those are the findings a matrix exists to surface.

A configuration is injected as environment variables for the duration of that run, so it reaches both
external SUTs (subprocesses inherit the environment) and in-process ones (which can read it) without any
change to a scenario or adapter. The environment is saved and restored around each run.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field

from .runner import run_suite
from .scenario import Suite
from .schema import RunReport, Status


@dataclass
class Matrix:
    """Named configurations. Each maps a config name to the environment overrides that define it."""
    name: str
    configs: dict[str, dict[str, str]] = field(default_factory=dict)


@contextmanager
def _env(overrides: dict[str, str]):
    saved = {k: os.environ.get(k) for k in overrides}
    os.environ.update({k: str(v) for k, v in overrides.items()})
    try:
        yield
    finally:
        for k, previous in saved.items():
            if previous is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = previous


@dataclass
class MatrixReport:
    matrix: str
    suite: str
    configs: dict[str, dict[str, str]]
    runs: dict[str, RunReport]                        # config name -> that config's run

    # -- shape ---------------------------------------------------------------
    def scenario_ids(self) -> list[str]:
        seen: list[str] = []
        for run in self.runs.values():
            for r in run.results:
                if r.id not in seen:
                    seen.append(r.id)
        return seen

    def status_grid(self) -> dict[str, dict[str, Status]]:
        """scenario -> {config -> status}."""
        grid: dict[str, dict[str, Status]] = {sid: {} for sid in self.scenario_ids()}
        for cfg, run in self.runs.items():
            for r in run.results:
                grid[r.id][cfg] = r.status
        return grid

    def metric_grid(self, metric: str) -> dict[str, dict[str, float]]:
        """scenario -> {config -> value} for a chosen metric (present cells only)."""
        out: dict[str, dict[str, float]] = {}
        for cfg, run in self.runs.items():
            for r in run.results:
                if metric in r.metrics:
                    out.setdefault(r.id, {})[cfg] = r.metrics[metric]
        return out

    def divergent_scenarios(self) -> list[str]:
        """Scenarios whose verdict is not the same across all configurations — the actionable finding."""
        divergent = []
        for sid, per_config in self.status_grid().items():
            if len({s for s in per_config.values()}) > 1:
                divergent.append(sid)
        return divergent

    def any_failure(self) -> bool:
        return any(r.status in (Status.FAIL, Status.ERROR)
                   for run in self.runs.values() for r in run.results)

    # -- rendering -----------------------------------------------------------
    def to_grid_text(self) -> str:
        configs = list(self.runs)
        grid = self.status_grid()
        glyph = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.ERROR: "ERR ", Status.SKIP: "skip"}
        w = max((len(s) for s in grid), default=8)
        header = "  " + "scenario".ljust(w) + "   " + "  ".join(c.center(8) for c in configs)
        lines = [header, "  " + "-" * (len(header) - 2)]
        for sid, per in grid.items():
            cells = "  ".join(glyph.get(per.get(c), "  - ").center(8) for c in configs)
            marker = "  ◀ diverges" if len({s for s in per.values()}) > 1 else ""
            lines.append("  " + sid.ljust(w) + "   " + cells + marker)
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps({
            "matrix": self.matrix, "suite": self.suite, "configs": self.configs,
            "status_grid": {s: {c: st.value for c, st in per.items()}
                            for s, per in self.status_grid().items()},
            "divergent": self.divergent_scenarios(),
            "runs": {cfg: run.to_dict() for cfg, run in self.runs.items()},
        }, indent=2, default=str)


def run_matrix(suite: Suite, matrix: Matrix, *, redact_output: bool = True,
               skip_tags: frozenset[str] | set[str] = frozenset()) -> MatrixReport:
    """Run ``suite`` once per configuration in ``matrix`` (env injected + restored) and aggregate."""
    skip = frozenset(skip_tags)
    runs: dict[str, RunReport] = {}
    for cfg_name, overrides in matrix.configs.items():
        with _env(overrides):
            runs[cfg_name] = run_suite(suite, redact_output=redact_output, skip_tags=skip)
    return MatrixReport(matrix.name, suite.name, dict(matrix.configs), runs)
