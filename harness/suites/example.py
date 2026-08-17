"""An example validation suite — the collateral the CLI runs by default.

It exercises both adapter kinds against real, deterministic work:

* in-process scenarios (a seeded Monte-Carlo estimate, a hashing throughput sim), and
* an external "station utility" driven as a subprocess that emits a ``LAB_RESULT`` contract, plus
* an optional scenario that drives the Java matching engine when it has been built — otherwise it
  SKIPs, the way a lab skips a device that isn't present.
"""

from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path

from ..adapters import CallableAdapter, CommandAdapter
from ..baseline import BaselinePolicy, MetricRule
from ..checks import ExitZero, MetricPresent, MetricThreshold, NoError, OutputContains
from ..matrix import Matrix
from ..scenario import Scenario, Suite

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ── in-process systems under test ────────────────────────────────────────────
def _estimate_pi(seed: int) -> dict:
    """Seeded Monte-Carlo π — same seed ⇒ same estimate, so this is a determinism anchor."""
    rng = random.Random(seed)
    n, inside = 20_000, 0
    for _ in range(n):
        x, y = rng.random(), rng.random()
        if x * x + y * y <= 1.0:
            inside += 1
    return {"pi_estimate": 4.0 * inside / n, "samples": n}


def _hash_throughput(seed: int) -> dict:
    """A small CPU workload; reports how many hashes/sec — a perf metric with a loose floor."""
    import hashlib
    data = bytes((seed + i) % 256 for i in range(1024))
    start = time.perf_counter()
    iters = 20_000
    for i in range(iters):
        hashlib.sha256(data + i.to_bytes(4, "little")).digest()
    elapsed = time.perf_counter() - start
    return {"hashes_per_sec": iters / elapsed, "iterations": iters}


# ── external station utility (subprocess with a result contract) ─────────────
_STATION_UTIL = (
    "import os, json;"
    "seed=int(os.environ.get('LAB_SEED','0'));"
    "print('station-utility: configuring device under test');"
    "print('LAB_RESULT ' + json.dumps({'answer': 42, 'seed_echo': seed}))"
)

# Reads the LAB_MODE configuration and reports a mode-dependent budget — used by the config matrix to
# show one suite producing comparable-but-different results across configurations.
_CONFIG_PROBE = (
    "import os, json;"
    "mode=os.environ.get('LAB_MODE','default');"
    "budget={'default':100,'fast':50,'safe':200}.get(mode,100);"
    "print(f'probe running in {mode} mode');"
    "print('LAB_RESULT ' + json.dumps({'budget': budget}))"
)


def _matching_engine_absent() -> str | None:
    classes = _REPO_ROOT / "backend" / "target" / "classes"
    if not (classes / "com/bonddesk/oms/matching/MatchingBenchmark.class").exists():
        return "matching engine not built (run: mvn -pl backend -am package)"
    return None


def _load_test_absent() -> str | None:
    cls = _REPO_ROOT / "backend" / "target" / "test-classes" / "com/bonddesk/exchange/OrderPathLoadTest.class"
    if not cls.exists():
        return "load test not built (run: mvn -pl backend -am test-compile)"
    return None


_BACKEND_CP = f"{_REPO_ROOT / 'backend' / 'target' / 'test-classes'}:{_REPO_ROOT / 'backend' / 'target' / 'classes'}"


SUITE = Suite("example", [
    Scenario("pi_monte_carlo", CallableAdapter(_estimate_pi), seed=7, tags=["accuracy", "fast"],
             checks=[NoError(), MetricPresent("pi_estimate"),
                     MetricThreshold("pi_estimate", ">", 3.0), MetricThreshold("pi_estimate", "<", 3.3)]),

    Scenario("hash_throughput", CallableAdapter(_hash_throughput), seed=1, tags=["perf", "fast"],
             checks=[NoError(), MetricThreshold("hashes_per_sec", ">", 10_000.0)]),

    Scenario("station_utility", CommandAdapter([sys.executable, "-c", _STATION_UTIL]),
             seed=99, tags=["external", "contract"],
             checks=[ExitZero(), OutputContains("configuring device"),
                     MetricThreshold("answer", "==", 42), MetricThreshold("seed_echo", "==", 99)]),

    Scenario("config_probe", CommandAdapter([sys.executable, "-c", _CONFIG_PROBE]),
             tags=["external", "config"],
             checks=[ExitZero(), MetricPresent("budget"), MetricThreshold("budget", ">", 0)]),

    Scenario("matching_engine_smoke",
             CommandAdapter(["java", "-cp", str(_REPO_ROOT / "backend" / "target" / "classes"),
                             "com.bonddesk.oms.matching.MatchingBenchmark", "200000", "50000"],
                            timeout=120),
             tags=["external", "device"], skip_if=_matching_engine_absent,
             checks=[ExitZero()]),

    # Performance gate: drive the matching path under concurrent load and assert throughput and tail
    # latency stay within bounds (a short run: 300ms/level, 8 instruments, up to 4 threads).
    Scenario("matching_load_gate",
             CommandAdapter(["java", "-cp", _BACKEND_CP,
                             "com.bonddesk.exchange.OrderPathLoadTest", "300", "8", "4"], timeout=120),
             tags=["external", "perf", "device"], skip_if=_load_test_absent,
             checks=[ExitZero(),
                     MetricThreshold("throughput_per_sec", ">", 300_000),
                     MetricThreshold("p99_ns", "<", 100_000)]),
])


# Quality-gate policy for this suite: accuracy is gated everywhere; throughput is gated only on
# comparable hardware (see baseline.py). Auto-loaded by the CLI when it loads this module's SUITE.
POLICY = BaselinePolicy(rules={
    "pi_estimate": MetricRule("exact", 0.05),        # seeded → must reproduce within 0.05 anywhere
    "hashes_per_sec": MetricRule("higher", 0.30),    # allow 30% slowdown before failing (CI-noise tolerant)
})

# Configuration matrix: run the whole suite under three modes. Auto-loaded by `--matrix` beside SUITE.
# All three pass here (the point is comparable results); config_probe's 'budget' differs by mode.
MATRIX = Matrix("modes", {
    "default": {},
    "fast": {"LAB_MODE": "fast"},
    "safe": {"LAB_MODE": "safe"},
})

