"""Demo: the parallel research runner.

Backtests a grid of one-line DSL signals over a shared price panel — first serially, then across CPU
cores — and shows the speedup, per-task fault isolation, and the ranked result table a sweep produces.
Self-contained: synthetic prices, no data or network needed.

    python run_parallel.py
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

from mds import engine as eng
from mds.parallel import backtest_signals


def _prices(n_days=3000, n_names=120):
    rng = np.random.default_rng(3)
    idx = pd.date_range("2010-01-01", periods=n_days, freq="B")
    cols = [f"S{i:03d}" for i in range(n_names)]
    steps = rng.normal(0.0003, 0.012, size=(n_days, n_names))
    return pd.DataFrame(100 * np.exp(np.cumsum(steps, axis=0)), index=idx, columns=cols)


def _grid() -> dict[str, str]:
    """A realistic parameter sweep — the case where parallelism pays: total work dwarfs the fixed
    per-worker startup cost. (For a handful of cheap backtests, spawn + data-pickling overhead wins and
    serial is faster; parallelism is a large-batch tool, not a free lunch.)"""
    windows = (2, 3, 5, 8, 13, 21, 34, 55, 89, 144)
    grid: dict[str, str] = {}
    for d in windows:
        grid[f"reversal_{d}"] = f"zscore(-ts_delta(close, {d}))"
        grid[f"momentum_{d}"] = f"zscore(ts_delta(close, {d}))"
        grid[f"tsrev_{d}"] = f"-zscore(ts_zscore(close, {d}))"
    for d in (5, 10, 20, 40, 60, 120):
        grid[f"lowvol_{d}"] = f"-zscore(ts_std(returns, {d}))"
    for d in (5, 10, 21, 42, 63):
        grid[f"accel_{d}"] = f"zscore(ts_delta(close, {d}) - ts_delta(close, {2 * d}))"
    grid["blend"] = "zscore(-ts_delta(close, 5)) + 0.5 * -zscore(ts_std(returns, 20))"
    grid["bad_signal"] = "zscore(does_not_exist)"        # deliberately broken → isolated, not fatal
    return grid


def main() -> None:
    px = _prices()
    grid = _grid()
    cfg = eng.BacktestConfig(rebalance=5, cost_bps=5.0)
    cores = os.cpu_count() or 1
    print(f"sweep: {len(grid)} signals over {px.shape[0]} days × {px.shape[1]} names "
          f"| {cores} cores available\n")

    t0 = time.perf_counter()
    serial = backtest_signals(grid, px, config=cfg, warmup=63, max_workers=1)
    t_serial = time.perf_counter() - t0

    t0 = time.perf_counter()
    parallel = backtest_signals(grid, px, config=cfg, warmup=63, max_workers=cores)
    t_parallel = time.perf_counter() - t0

    print(f"{'serial (1 worker)':<24}: {t_serial:6.2f}s")
    print(f"{'parallel (' + str(cores) + ' workers)':<24}: {t_parallel:6.2f}s   "
          f"→  {t_serial / t_parallel:4.1f}× faster\n")

    ok = [s for s in parallel if s["ok"]]
    failed = [s for s in parallel if not s["ok"]]
    print(f"fault isolation: {len(failed)} signal(s) failed but the sweep completed — "
          f"{[f['name'] for f in failed]}\n")

    print("top signals by Sharpe (synthetic data — a plumbing demo, not an edge):")
    print(f"    {'signal':<14}{'Sharpe':>8}{'turnover':>10}")
    for s in sorted(ok, key=lambda r: r["sharpe"], reverse=True)[:6]:
        print(f"    {s['name']:<14}{s['sharpe']:>8.2f}{s['turnover_ann']:>10.1f}")


if __name__ == "__main__":
    main()
