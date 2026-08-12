"""Content-addressed cache for compiled signals — the incremental-computation layer over the DSL.

Evaluating a signal is a pure function of *(the expression, the input data it reads)*. So the result
can be memoised under a key that is a hash of exactly those two things — the same idea that makes Bazel
and dbt skip work that can't have changed:

    key = hash( AST fingerprint  ‖  content hash of each data column the signal actually reads )

Two consequences fall out for free:

* **Automatic, precise invalidation.** Change ``close`` and every signal that reads ``close`` gets a new
  key (a miss, a recompute); a signal that reads only ``volume`` still hits. Nothing has to be manually
  expired — a changed input simply addresses a different cache slot.
* **Persistence.** The data hash is deterministic across processes, so a result written to disk on one
  run is found on the next. Repeated backtests / parameter sweeps / capacity curves that re-evaluate
  the same signal on the same data pay the evaluation cost once.

Two tiers: a small in-process LRU in front of a content-addressed Parquet store on disk.
"""

from __future__ import annotations

import hashlib
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

from .alphadsl import CompiledSignal, compile_signal
from .store import DATA_DIR, read_parquet, write_parquet


def _frame_content_hash(df: pd.DataFrame) -> str:
    """A fast, deterministic full-content hash of a panel: shape, columns, index bounds, and every
    cell value.

    Hashing has to be much cheaper than re-evaluating the signal or the cache defeats its own purpose,
    so for the common numeric panel we blake2b the raw contiguous bytes (a single memcpy + a ~GB/s
    hash) rather than pandas' slower row-wise hash. Falls back to the general hash for non-float frames.
    """
    h = hashlib.blake2b(digest_size=16)
    h.update(repr(df.shape).encode())
    h.update("|".join(map(str, df.columns)).encode())
    idx = df.index
    if len(idx):
        h.update(f"{idx[0]}|{idx[-1]}|{len(idx)}".encode())
    try:
        values = np.ascontiguousarray(df.to_numpy(dtype="float64"))
        h.update(values.tobytes())                          # NaN has a canonical float64 bit pattern
    except (TypeError, ValueError):
        h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()


class SignalCache:
    """Memoise compiled-signal evaluation, keyed on (expression, the data it reads)."""

    def __init__(self, cache_dir: str | Path | None = None, *, memory_items: int = 128):
        self.dir = Path(cache_dir) if cache_dir is not None else DATA_DIR / "sigcache"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._mem: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._mem_cap = memory_items
        self._stats: Counter[str] = Counter()

    # -- keying --------------------------------------------------------------
    def key(self, signal: str | CompiledSignal, env: dict[str, pd.DataFrame]) -> str:
        """The content address for evaluating ``signal`` against ``env`` — code hash ‖ data hash."""
        sig = compile_signal(signal) if isinstance(signal, str) else signal
        parts = [sig.fingerprint]
        for col in sorted(sig.columns):                     # only the columns the signal reads
            if col not in env:
                raise KeyError(f"signal reads column {col!r} not present in env")
            parts.append(f"{col}={_frame_content_hash(env[col])}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]

    # -- evaluation ----------------------------------------------------------
    def evaluate(self, signal: str | CompiledSignal, env: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Return the signal's panel, from cache when the (expression, data) is unchanged."""
        sig = compile_signal(signal) if isinstance(signal, str) else signal
        k = self.key(sig, env)

        cached = self._mem.get(k)
        if cached is not None:
            self._mem.move_to_end(k)
            self._stats["memory_hits"] += 1
            self._stats["hits"] += 1
            return cached.copy()

        path = self.dir / f"{k}.parquet"
        if path.exists():
            df = read_parquet(path)
            self._remember(k, df)
            self._stats["disk_hits"] += 1
            self._stats["hits"] += 1
            return df.copy()

        self._stats["misses"] += 1
        result = sig.evaluate(env)
        if isinstance(result, pd.DataFrame):
            write_parquet(result, path)
            self._remember(k, result)
            self._stats["writes"] += 1
            return result.copy()
        return result                                       # scalar signal: nothing to cache

    # -- housekeeping --------------------------------------------------------
    def _remember(self, key: str, df: pd.DataFrame) -> None:
        self._mem[key] = df
        self._mem.move_to_end(key)
        while len(self._mem) > self._mem_cap:
            self._mem.popitem(last=False)                   # evict least-recently-used

    def clear(self, disk: bool = True) -> None:
        """Drop the in-memory tier (and, by default, delete the on-disk store)."""
        self._mem.clear()
        if disk:
            for p in self.dir.glob("*.parquet"):
                p.unlink()

    @property
    def stats(self) -> dict[str, float]:
        s = {k: self._stats.get(k, 0) for k in ("hits", "misses", "memory_hits", "disk_hits", "writes")}
        total = s["hits"] + s["misses"]
        s["hit_rate"] = round(s["hits"] / total, 3) if total else 0.0
        return s
