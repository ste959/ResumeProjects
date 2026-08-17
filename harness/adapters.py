"""Adapters — the seam between the harness and a system under test (SUT).

An adapter knows *how to drive one kind of SUT* and hand back a uniform :class:`AdapterOutcome`, so the
runner and the checks stay agnostic to whether the thing under test is an in-process function or an
external binary on a lab station.

* :class:`CallableAdapter` runs a Python callable in-process — for fast, fully deterministic scenarios.
* :class:`CommandAdapter` drives an external command (the Java matching engine, a C#/PowerShell station
  utility, anything), passing the run seed in via an environment variable and collecting results the
  tool prints as ``LAB_RESULT {json}`` lines. This is the real lab pattern: drive a device, collect its
  results, don't couple to its internals.

The ``ok`` flag separates *infra faults* (the adapter couldn't run the SUT — a timeout, a missing
binary) from *the SUT's own behaviour* (a non-zero exit or a metric out of range), which is a check's
job to judge. That distinction is what lets the runner report ERROR vs FAIL correctly.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import traceback
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class AdapterOutcome:
    ok: bool                                   # did the SUT run at all (no infra fault)?
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None                   # set only on an infra fault


class CallableAdapter:
    """Run an in-process callable ``fn(seed) -> dict | None``; the returned dict becomes the metrics."""

    def __init__(self, fn: Callable[[int], dict | None]):
        self._fn = fn

    def run(self, seed: int) -> AdapterOutcome:
        try:
            out = self._fn(seed)
        except Exception as e:                  # noqa: BLE001 — an exception here is an infra/scenario fault
            return AdapterOutcome(ok=False, error=f"{type(e).__name__}: {e}",
                                  stderr=traceback.format_exc())
        metrics = {str(k): v for k, v in out.items()} if isinstance(out, dict) else {}
        return AdapterOutcome(ok=True, exit_code=0, metrics=metrics)


class CommandAdapter:
    """Drive an external command and collect ``LAB_RESULT {json}`` metrics from its stdout."""

    _RESULT_RE = re.compile(r"^LAB_RESULT\s+(\{.*\})\s*$", re.MULTILINE)

    def __init__(self, argv: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None,
                 timeout: float | None = None, seed_env: str = "LAB_SEED"):
        self._argv = argv
        self._cwd = cwd
        self._env = env
        self._timeout = timeout
        self._seed_env = seed_env

    def run(self, seed: int) -> AdapterOutcome:
        env = {**os.environ, **(self._env or {})}
        if self._seed_env:
            env[self._seed_env] = str(seed)                # let the SUT seed itself deterministically
        try:
            proc = subprocess.run(self._argv, cwd=self._cwd, env=env, capture_output=True,
                                  text=True, timeout=self._timeout)
        except subprocess.TimeoutExpired as e:
            return AdapterOutcome(ok=False, error=f"timeout after {self._timeout}s",
                                  stdout=e.stdout or "", stderr=e.stderr or "")
        except OSError as e:
            return AdapterOutcome(ok=False, error=f"failed to start {self._argv[0]!r}: {e}")
        return AdapterOutcome(ok=True, exit_code=proc.returncode, stdout=proc.stdout,
                              stderr=proc.stderr, metrics=self._parse_results(proc.stdout))

    @classmethod
    def _parse_results(cls, stdout: str) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for match in cls._RESULT_RE.finditer(stdout):
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                metrics.update(payload)
        return metrics
