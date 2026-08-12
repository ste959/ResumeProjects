"""Demo: the content-addressed signal cache.

Shows the incremental-computation win — repeated evaluation of the same signal on the same data is
paid once — plus precise invalidation (a changed input is a genuine recompute; an unrelated change is
still a hit). Self-contained: synthetic panels, no data or network needed.

    python run_sigcache.py
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

from mds import alphadsl as dsl
from mds.sigcache import SignalCache


def _panels(n_days=4000, n_names=300):
    rng = np.random.default_rng(11)
    idx = pd.date_range("2005-01-01", periods=n_days, freq="B")
    cols = [f"S{i:03d}" for i in range(n_names)]
    steps = rng.normal(0.0002, 0.012, size=(n_days, n_names))
    close = pd.DataFrame(100 * np.exp(np.cumsum(steps, axis=0)), index=idx, columns=cols)
    volume = pd.DataFrame(rng.lognormal(12, 0.6, size=(n_days, n_names)), index=idx, columns=cols)
    return {"close": close, "volume": volume, "returns": close.pct_change()}


def main() -> None:
    env = _panels()
    # A non-trivial signal: several rolling passes + cross-sectional ops over 300 names × 4000 days.
    src = "zscore(ts_delta(close, 20)) - 0.5 * zscore(ts_std(returns, 60)) + 0.25 * rank(ts_mean(volume, 20))"
    repeats = 25
    print(f"panel: {env['close'].shape[0]} days × {env['close'].shape[1]} names   "
          f"signal: {src}\n")

    # --- baseline: re-evaluate every time (what a parameter sweep does today) ---
    t0 = time.perf_counter()
    for _ in range(repeats):
        dsl.evaluate(src, env)
    uncached = time.perf_counter() - t0

    # --- cached: compute once, then reuse (identical expression + data) ---
    tmp = Path(tempfile.mkdtemp(prefix="sigcache_demo_"))
    try:
        cache = SignalCache(tmp)
        t0 = time.perf_counter()
        for _ in range(repeats):
            cache.evaluate(src, env)
        cached = time.perf_counter() - t0

        print(f"{'re-evaluate every time':<28}: {uncached:7.3f}s  ({repeats} evaluations)")
        print(f"{'content-addressed cache':<28}: {cached:7.3f}s  "
              f"(1 miss + {repeats - 1} hits)   →  {uncached / cached:5.1f}× faster")
        print(f"cache stats                 : {cache.stats}\n")

        print("Precise invalidation:")
        env_changed_close = {**env, "close": env["close"] * 1.001}
        env_changed_vol = {**env, "volume": env["volume"] * 2.0}
        before = cache.stats["misses"]
        cache.evaluate(src, env_changed_close)   # close is an input → recompute
        after_close = cache.stats["misses"]
        cache.evaluate(src, env_changed_vol)     # volume is also an input → recompute
        # A signal over close only is unaffected by a volume change:
        cache.evaluate("zscore(close)", env)                       # miss (new signal)
        m1 = cache.stats["misses"]
        cache.evaluate("zscore(close)", env_changed_vol)           # hit: volume isn't its input
        m2 = cache.stats["misses"]
        print(f"    changed close  → recompute : {after_close > before}")
        print(f"    zscore(close), then change only volume → still a hit : {m2 == m1}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
