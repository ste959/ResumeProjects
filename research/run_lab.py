"""Quant Lab — the platform demo: many strategies, ONE pipeline.

Every strategy below is defined against the same `engine.Strategy` interface and run through the same
walk-forward engine, the same excess-of-cash evaluation, the same selection-aware gauntlet, and the same
tearsheet + attribution. Adding a strategy is ~15 lines; it inherits the entire concept→backtest→validate
→report flow for free. This is the spine a research desk builds on.

    python run_lab.py            # fetch (or load cached) ETF bars, run all strategies, compare + report
    python run_lab.py --refresh  # re-fetch from Alpaca

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys). The engine + strategies are pure and unit-tested
(tests/test_engine.py); this driver just supplies real data.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import engine as eng
from mds import strategies_lib as sl
from mds import trend as tr

START, END = "2020-07-27", "2026-07-02"
RF_PROXY = "BIL"
CACHE = pathlib.Path(__file__).parent / "data" / "cache" / "trend_total.parquet"


def _load(refresh: bool) -> tuple[pd.DataFrame, pd.Series]:
    """Total-return panel for the diversified universe + the daily risk-free (BIL). Cached for determinism."""
    syms = list(tr.UNIVERSE) + [RF_PROXY]
    if CACHE.exists() and not refresh:
        panel = pd.read_parquet(CACHE)
    else:
        panel = ad.close_panel(ad.fetch_bars(syms, START, END, adjustment="all")).reindex(columns=syms).dropna()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(CACHE)
    return panel[list(tr.UNIVERSE)], panel[RF_PROXY].pct_change()


def main() -> None:
    prices, rf = _load("--refresh" in sys.argv)
    syms = list(tr.UNIVERSE)
    cfg = eng.BacktestConfig(rebalance=21, cost_bps=10.0, rf=rf)

    # One registry of strategies — allocation, benchmark, and trend — all behind one interface.
    strategies = [
        sl.EqualWeight(syms),
        sl.SixtyForty("SPY", "IEF"),
        sl.RiskParity(syms),
        sl.MinVariance(syms),
        sl.TimeSeriesMomentum(syms),
    ]

    print(f"Quant Lab · {len(syms)}-market universe · {prices.index[0].date()} → {prices.index[-1].date()} · "
          f"10 bps cost, monthly rebalance · excess of {RF_PROXY}")
    print(f"{len(strategies)} strategies, ONE engine + gauntlet + tearsheet.\n")

    out = eng.compare(strategies, prices, cfg)
    results = sorted(out["results"], key=lambda r: r.stats["sharpe"], reverse=True)

    hdr = f"{'strategy':<16}{'ann ret':>9}{'ann vol':>9}{'exSharpe':>9}{'HAC t':>7}{'max DD':>9}{'Sortino':>9}{'gross':>7}"
    print(hdr); print("-" * len(hdr))
    for r in results:
        s = r.stats
        print(f"{r.name:<16}{s['ann_return']*100:>8.1f}%{s['ann_vol']*100:>8.1f}%{s['sharpe']:>9.2f}"
              f"{s['hac_t']:>7.1f}{s['max_drawdown']*100:>8.1f}%{s['sortino']:>9.2f}{r.avg_gross:>6.2f}x")

    g = out["gauntlet"]
    clears = abs(g["best_hac_t"]) >= g["bonferroni_t"]
    powered = g["best_sharpe_ann"] >= g["min_detectable_sharpe"]
    print(f"\nSelection-aware gauntlet ({g['n_strategies']} strategies, {g['n_days']} days):")
    print(f"  best {g['best']} (ann {g['best_sharpe_ann']}, HAC t {g['best_hac_t']})  |  "
          f"bar |t|>{g['bonferroni_t']} → {'CLEARS' if clears else 'FAILS'}  |  DSR {g['deflated_sharpe']}  "
          f"PBO {g['pbo']}  min-detectable {g['min_detectable_sharpe']} → {'powered' if powered else 'UNDERPOWERED'}")

    best = results[0]
    print(f"\nTearsheet — best by excess Sharpe:")
    eng.print_tearsheet(best)
    at = eng.attribution(best, prices, groups=tr.SLEEVES)
    print("   P&L by sleeve:  " + "  ".join(f"{k} {v*100:+.1f}%" for k, v in at["per_group"].items()))

    print(f"\nThe point: every row above ran through the identical engine, evaluation, and gauntlet. A new "
          f"idea becomes a subclass with a `target_weights` method and inherits the whole pipeline — "
          f"concept → walk-forward backtest → overfitting gauntlet → attribution → tearsheet.")


if __name__ == "__main__":
    main()
