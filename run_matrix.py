"""Demo: configuration-matrix orchestration.

Runs one suite across three configurations and shows the two things a matrix is for: **comparable
results** (the same metric measured under each config) and **config-dependent failures** (a scenario
that passes under some configs and fails under others — the finding a matrix exists to surface).

Self-contained: the systems under test are small subprocesses that read the injected LAB_MODE.

    python run_matrix.py
"""

from __future__ import annotations

import sys

from harness.adapters import CommandAdapter
from harness.checks import ExitZero, MetricPresent, MetricThreshold
from harness.matrix import Matrix, run_matrix
from harness.scenario import Scenario, Suite

# A SUT that reports a mode-dependent "power budget".
_PROBE = (
    "import os, json;"
    "mode=os.environ.get('LAB_MODE','default');"
    "budget={'default':100,'fast':50,'safe':200}.get(mode,100);"
    "print('LAB_RESULT ' + json.dumps({'budget': budget}))"
)


def main() -> None:
    suite = Suite("power", [
        # Always passes; its 'budget' metric differs by config — comparable results.
        Scenario("probe", CommandAdapter([sys.executable, "-c", _PROBE]),
                 checks=[ExitZero(), MetricPresent("budget")]),
        # Requires budget >= 150 — so it PASSES only under 'safe' and FAILS under 'default'/'fast'.
        # That is a config-dependent failure: the matrix pinpoints which configs break it.
        Scenario("needs_high_budget", CommandAdapter([sys.executable, "-c", _PROBE]),
                 checks=[MetricThreshold("budget", ">=", 150)]),
    ])
    matrix = Matrix("power-modes", {"default": {}, "fast": {"LAB_MODE": "fast"},
                                    "safe": {"LAB_MODE": "safe"}})

    report = run_matrix(suite, matrix)

    print(f"\nconfig matrix '{matrix.name}': {suite.name} × {len(matrix.configs)} configs\n")
    print(report.to_grid_text())

    print("\ncomparable metric — 'budget' per config:")
    for scenario, per_config in report.metric_grid("budget").items():
        cells = "  ".join(f"{c}={v:g}" for c, v in per_config.items())
        print(f"    {scenario:<18} {cells}")

    divergent = report.divergent_scenarios()
    print(f"\nconfig-dependent failures: {', '.join(divergent) if divergent else 'none'}")
    if divergent:
        grid = report.status_grid()
        for sid in divergent:
            failing = [c for c, s in grid[sid].items() if s.value in ("FAIL", "ERROR")]
            print(f"    '{sid}' fails under: {', '.join(failing)}  (passes under the rest)")


if __name__ == "__main__":
    main()
