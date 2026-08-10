"""Generate the trader/researcher-facing reports — an HTML tearsheet per strategy and a leaderboard.

Runs the strategy set through the one engine + gauntlet, then writes self-contained HTML (open it in any
browser — no server, no dependencies) to `research/reports/`.

    python run_report.py [--refresh]

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys). The report rendering is pure and unit-tested
(tests/test_report.py); this driver supplies real data.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import engine as eng
from mds import report as rp
from mds import strategies_lib as sl
from mds import trend as tr

START, END = "2020-07-27", "2026-07-02"
RF_PROXY = "BIL"
CACHE = pathlib.Path(__file__).parent / "data" / "cache" / "trend_total.parquet"
REPORTS = pathlib.Path(__file__).parent / "reports"


def _load(refresh: bool):
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

    strategies = [sl.EqualWeight(syms), sl.SixtyForty("SPY", "IEF"), sl.RiskParity(syms),
                  sl.MinVariance(syms), sl.TimeSeriesMomentum(syms)]
    out = eng.compare(strategies, prices, cfg)
    REPORTS.mkdir(parents=True, exist_ok=True)

    lb = REPORTS / "leaderboard.html"
    lb.write_text(rp.leaderboard_html(out["results"], out["gauntlet"]))
    written = [lb]
    for r in out["results"]:
        path = REPORTS / f"tearsheet_{r.name.replace('/', '-')}.html"
        path.write_text(rp.tearsheet_html(r, prices, rf=rf, sleeves=tr.SLEEVES))
        written.append(path)

    print(f"Wrote {len(written)} self-contained HTML reports to {REPORTS}/:")
    for p in written:
        print(f"  {p.name}")
    print("\nOpen any of them in a browser — equity curve, drawdown, rolling Sharpe, monthly-return "
          "heatmap, VaR/ES + risk contribution, and P&L attribution, all inlined. The leaderboard ranks "
          "every strategy through the same selection-aware gauntlet.")


if __name__ == "__main__":
    main()
