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
import shlex
import signal
import subprocess
import traceback
from dataclasses import dataclass, field
from typing import Callable

_MAX_CAPTURE = 64 * 1024        # cap stored stdout/stderr so a chatty SUT can't bloat results/bundles


def _cap(text: str | None) -> str:
    if not text:
        return ""
    if len(text) <= _MAX_CAPTURE:
        return text
    half = _MAX_CAPTURE // 2
    return f"{text[:half]}\n...[{len(text) - _MAX_CAPTURE} chars truncated]...\n{text[-half:]}"


def _kill_group(proc: "subprocess.Popen") -> None:
    """Kill the SUT's whole process group, so a wrapper that spawned the real engine doesn't orphan it."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:
            proc.kill()                                    # Windows: no process groups here
    except (ProcessLookupError, PermissionError, OSError):
        pass


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

    def describe(self, seed: int) -> str:
        name = getattr(self._fn, "__qualname__", repr(self._fn))
        return f"in-process callable {name} (seed={seed})"

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

    def describe(self, seed: int) -> str:
        """The exact shell command to reproduce this run, with the seed pinned via its env var."""
        prefix = f"{self._seed_env}={seed} " if self._seed_env else ""
        return prefix + shlex.join(self._argv)

    def run(self, seed: int) -> AdapterOutcome:
        env = {**os.environ, **(self._env or {})}
        if self._seed_env:
            env[self._seed_env] = str(seed)                # let the SUT seed itself deterministically
        # start_new_session puts the SUT in its own process group so a timeout can reap the whole tree.
        try:
            proc = subprocess.Popen(self._argv, cwd=self._cwd, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, start_new_session=True)
        except OSError as e:
            return AdapterOutcome(ok=False, error=f"failed to start {self._argv[0]!r}: {e}")
        try:
            stdout, stderr = proc.communicate(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            stdout, stderr = proc.communicate()            # drain whatever the killed SUT left
            return AdapterOutcome(ok=False, error=f"timeout after {self._timeout}s",
                                  stdout=_cap(stdout), stderr=_cap(stderr))
        # Parse the full stdout for the result contract, then cap what we store.
        metrics = self._parse_results(stdout)
        return AdapterOutcome(ok=True, exit_code=proc.returncode, stdout=_cap(stdout),
                              stderr=_cap(stderr), metrics=metrics)

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
