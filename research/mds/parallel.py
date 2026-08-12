"""Parallel research runner — the execution layer over the DSL and its cache.

Signals are independent, and a research sweep evaluates many of them (or backtests many of them) over
the *same* data. That is embarrassingly parallel across CPU cores, so this module fans the work out
over a process pool.

Design decisions that make it a real parallel component rather than a ``Pool.map`` one-liner:

* **Shared data, sent once per worker.** The panel/price data is handed to each worker exactly once via
  the pool *initializer* (not re-pickled per task), and tasks are just tiny signal strings. That keeps
  inter-process transfer proportional to ``workers``, not ``tasks``.
* **Per-task fault isolation.** A signal that fails to compile or evaluate returns an error *result*;
  the batch keeps going. One bad signal never takes down the sweep.
* **Deterministic aggregation.** Results come back in input order regardless of which worker finished
  first or how many workers there are — the output of a sweep can't depend on the scheduler.
* **Composes with the cache.** Workers open the *same* on-disk content-addressed cache; because the key
  is a content hash, cache reads need no locking and writes are idempotent (same key ⇒ same bytes), so
  redundant work anywhere in the grid is computed once and shared across processes.

Processes (not threads) because the work is CPU-bound NumPy; a further optimisation would place the
shared panels in ``multiprocessing.shared_memory`` to avoid the per-worker pickle entirely.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import pandas as pd

from . import alphadsl as dsl
from . import engine as eng
from .dslstrategy import DslStrategy
from .sigcache import SignalCache


@dataclass
class SignalResult:
    """Outcome of evaluating one signal — either a panel or the error that isolated it."""
    signal: str
    ok: bool
    panel: pd.DataFrame | None = None
    error: str | None = None


def _resolve_workers(max_workers: int | None, n_tasks: int) -> int:
    if max_workers is not None:
        return max(1, min(max_workers, n_tasks))
    return max(1, min(n_tasks, os.cpu_count() or 1))


def _context() -> mp.context.BaseContext:
    """Prefer ``forkserver``: workers are forked from a clean, single-threaded server process, which
    (a) sidesteps the well-known deadlock hazard of ``fork()``-ing a multi-threaded parent, and
    (b) pays the heavy pandas/mds import cost once in the server rather than in every worker (the cost
    that makes plain ``spawn`` slower than serial for this workload). Falls back to the platform default
    (``spawn`` on Windows)."""
    available = mp.get_all_start_methods()
    for method in ("forkserver", "fork"):
        if method in available:
            return mp.get_context(method)
    return mp.get_context()


def _run(worker_fn, tasks, init_fn, initargs, workers):
    """Fan ``tasks`` out to ``worker_fn`` across processes, with the shared read-only context built once
    per worker by ``init_fn``. ``init_fn`` also runs in the parent to serve the serial path. Results are
    returned in input order, so a sweep's output never depends on the scheduler."""
    init_fn(*initargs)                                   # parent context (serial path)
    if workers == 1 or len(tasks) <= 1:
        return [worker_fn(t) for t in tasks]
    with ProcessPoolExecutor(max_workers=workers, mp_context=_context(),
                             initializer=init_fn, initargs=initargs) as pool:
        return list(pool.map(worker_fn, tasks))


# ── evaluate_signals ─────────────────────────────────────────────────────────
# Worker-global context, populated once per process by the initializer.
_EVAL_ENV: dict[str, pd.DataFrame] | None = None
_EVAL_CACHE: SignalCache | None = None


def _eval_init(env: dict[str, pd.DataFrame], cache_dir: str | None) -> None:
    global _EVAL_ENV, _EVAL_CACHE
    _EVAL_ENV = env
    _EVAL_CACHE = SignalCache(cache_dir) if cache_dir is not None else None


def _eval_one(signal: str) -> SignalResult:
    try:
        panel = (_EVAL_CACHE.evaluate(signal, _EVAL_ENV) if _EVAL_CACHE is not None
                 else dsl.evaluate(signal, _EVAL_ENV))
        return SignalResult(signal, True, panel=panel)
    except Exception as e:                       # noqa: BLE001 — isolate any per-signal failure
        return SignalResult(signal, False, error=f"{type(e).__name__}: {e}")


def evaluate_signals(signals, env, *, max_workers: int | None = None,
                     cache: SignalCache | None = None) -> list[SignalResult]:
    """Evaluate many signal expressions over a shared ``env``, in parallel across processes.

    Returns one :class:`SignalResult` per input signal, in input order. A signal that fails is reported
    (``ok=False``) rather than raising. Pass a :class:`SignalCache` to share memoised results across
    workers and runs.
    """
    signals = list(signals)
    cache_dir = str(cache.dir) if cache is not None else None
    workers = _resolve_workers(max_workers, len(signals) or 1)
    return _run(_eval_one, signals, _eval_init, (env, cache_dir), workers)


# ── backtest_signals ─────────────────────────────────────────────────────────
_BT_PRICES: pd.DataFrame | None = None
_BT_CFG: eng.BacktestConfig | None = None
_BT_SYMS: list[str] | None = None
_BT_WARMUP: int = 252
_BT_EXTRA: dict[str, pd.DataFrame] | None = None
_BT_CACHE: SignalCache | None = None


def _bt_init(prices, cfg, syms, warmup, extra, cache_dir) -> None:
    global _BT_PRICES, _BT_CFG, _BT_SYMS, _BT_WARMUP, _BT_EXTRA, _BT_CACHE
    _BT_PRICES, _BT_CFG, _BT_SYMS, _BT_WARMUP = prices, cfg, syms, warmup
    _BT_EXTRA = extra
    _BT_CACHE = SignalCache(cache_dir) if cache_dir is not None else None


def _bt_one(item: tuple[str, str]) -> dict:
    name, expr = item
    try:
        strat = DslStrategy(expr, _BT_SYMS, name=name, warmup=_BT_WARMUP,
                            extra_panels=_BT_EXTRA, cache=_BT_CACHE)
        r = eng.run(strat, _BT_PRICES, _BT_CFG)
        return {"name": name, "signal": expr, "ok": True, "sharpe": r.stats["sharpe"],
                "ann_return": r.stats["ann_return"], "turnover_ann": r.turnover_ann,
                "avg_gross": r.avg_gross}
    except Exception as e:                       # noqa: BLE001
        return {"name": name, "signal": expr, "ok": False, "error": f"{type(e).__name__}: {e}"}


def backtest_signals(signals: dict[str, str], prices: pd.DataFrame, *,
                     config: eng.BacktestConfig | None = None, symbols: list[str] | None = None,
                     warmup: int = 252, extra_panels: dict[str, pd.DataFrame] | None = None,
                     max_workers: int | None = None, cache: SignalCache | None = None) -> list[dict]:
    """Backtest many one-line DSL signals over shared ``prices``, in parallel — a research sweep.

    ``signals`` maps a name to a DSL expression. Returns a compact summary dict per signal (Sharpe,
    return, turnover, gross) in input order — deliberately small so the inter-process payload stays
    tiny — with failures reported rather than raised.
    """
    items = list(signals.items())
    cfg = config or eng.BacktestConfig()
    syms = symbols if symbols is not None else list(prices.columns)
    cache_dir = str(cache.dir) if cache is not None else None
    workers = _resolve_workers(max_workers, len(items) or 1)
    return _run(_bt_one, items, _bt_init, (prices, cfg, syms, warmup, extra_panels, cache_dir), workers)
