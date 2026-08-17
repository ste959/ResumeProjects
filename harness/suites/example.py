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


def _matching_engine_absent() -> str | None:
    classes = _REPO_ROOT / "backend" / "target" / "classes"
    if not (classes / "com/bonddesk/oms/matching/MatchingBenchmark.class").exists():
        return "matching engine not built (run: mvn -pl backend -am package)"
    return None


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

    Scenario("matching_engine_smoke",
             CommandAdapter(["java", "-cp", str(_REPO_ROOT / "backend" / "target" / "classes"),
                             "com.bonddesk.oms.matching.MatchingBenchmark", "200000", "50000"],
                            timeout=120),
             tags=["external", "device"], skip_if=_matching_engine_absent,
             checks=[ExitZero()]),
])


# Quality-gate policy for this suite: accuracy is gated everywhere; throughput is gated only on
# comparable hardware (see baseline.py). Auto-loaded by the CLI when it loads this module's SUITE.
POLICY = BaselinePolicy(rules={
    "pi_estimate": MetricRule("exact", 0.05),        # seeded → must reproduce within 0.05 anywhere
    "hashes_per_sec": MetricRule("higher", 0.30),    # allow 30% slowdown before failing (CI-noise tolerant)
})

