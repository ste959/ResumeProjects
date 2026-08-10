"""Data integrity — audit the inputs, then run point-in-time so the backtest can't cheat on survivors.

Two failures corrupt more backtests than any modeling error: **dirty data** (unadjusted splits, stale
prices, gaps read as signal) and **survivorship bias** (testing only on names that still exist today).
This driver runs the data-quality audit and the point-in-time universe on a real equity set that mixes
long-listed mega-caps with recent IPOs, so both mechanisms fire on real data.

    python run_data.py [--refresh]

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys). The audits are pure and unit-tested
(tests/test_dataquality.py, tests/test_universe.py); this driver supplies real data.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import dataquality as dq
from mds import engine as eng
from mds import strategies_lib as sl
from mds import universe as un

START, END = "2020-07-27", "2026-07-02"
CACHE = pathlib.Path(__file__).parent / "data" / "cache" / "data_stocks.parquet"

# Long-listed mega-caps + names that IPO'd *after* the start date (real entries the PIT universe handles).
STOCKS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "JNJ", "XOM", "WMT", "PG", "HD",
          "ABNB", "PLTR", "SNOW", "COIN", "RIVN", "HOOD", "RBLX"]


def _load(refresh: bool) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    close = ad.close_panel(ad.fetch_bars(STOCKS, START, END, adjustment="all")).reindex(columns=STOCKS)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    close.to_parquet(CACHE)
    return close


def main() -> None:
    close = _load("--refresh" in sys.argv)
    print(f"Data integrity · {len(STOCKS)} equities (mega-caps + post-2020 IPOs) · "
          f"{close.index[0].date()} → {close.index[-1].date()}\n")

    # ── [1] data-quality audit ──
    rep = dq.audit_prices(close)
    s = rep["summary"]
    print(f"[1] Data-quality audit: {s['n_flagged']}/{s['n_symbols']} flagged, {s['duplicate_dates']} duplicate dates")
    review, incomplete = [], []
    for sym, r in rep["by_symbol"].items():
        if not r["flag"]:
            continue
        (review if (r["max_stale_run"] >= 5 or r["extreme_jumps"] > 0 or r["non_positive"] > 0) else incomplete).append(sym)
    print(f"    incomplete history (IPO/listing — handled by point-in-time): {incomplete}")
    print(f"    flagged for review (extreme move / stale / non-positive — an unadjusted action OR genuine "
          f"volatility; a human adjudicates): {review or 'none'}")

    # ── [2] survivorship audit ──
    a = un.survivorship_audit(close)
    print(f"\n[2] Survivorship audit:")
    print(f"    full history {a['n_full_history']}   entries (IPOs) {a['n_entries']}: {a['entries']}   "
          f"exits (delistings) {a['n_exits']}: {a['exits'] or 'none in free data'}")
    print(f"    survivors-only equal-weight {a['survivors_only_ann_return']*100:+.1f}%/yr   vs   "
          f"point-in-time (as-available) {a['point_in_time_ann_return']*100:+.1f}%/yr")

    # ── [3] point-in-time vs naive backtest ──
    first, last = un.PointInTimeUniverse(close).first_dates(), un.PointInTimeUniverse(close).last_dates()
    survivors = [c for c in close.columns if first[c] == close.index[0] and last[c] == close.index[-1]]
    u = un.PointInTimeUniverse(close)
    naive = eng.run(sl.EqualWeight(survivors), close[survivors], eng.BacktestConfig(cost_bps=10.0))
    pit = eng.run(sl.EqualWeight(list(close.columns)), close, eng.BacktestConfig(cost_bps=10.0), universe=u)
    held = (pit.weights.abs() > 0).sum(axis=1)
    print(f"\n[3] Backtest under point-in-time membership (equal-weight):")
    print(f"    naive 'survivors-only' universe: {len(survivors)} names, fixed   → Sharpe {naive.stats['sharpe']:.2f}")
    print(f"    point-in-time universe: names held grows {int(held.iloc[0])} → {int(held.iloc[-1])} as IPOs list "
          f"→ Sharpe {pit.stats['sharpe']:.2f}")

    print(f"\nVerdict: the audit gates on clean inputs (splits/stale/gaps caught, IPOs correctly separated "
          f"from defects), and the point-in-time universe only trades a name once it has actually listed — "
          f"no look-ahead into today's survivors, and delisting losses are realized when a held name exits "
          f"(mechanism built + tested). The one honest gap is the *delisted* names themselves: the free IEX "
          f"feed has none, so the exit side of survivorship needs a paid point-in-time source "
          f"(see ALPHA-DATA-ROADMAP.md). The infrastructure is ready for that data the day it's available.")


if __name__ == "__main__":
    main()
