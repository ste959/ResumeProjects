#!/usr/bin/env python3
"""Run the BTC/ETH statistical-arbitrage study and print an honest report.

Usage:  python run_statarb.py            (hourly candles, cached as Parquet)
        python run_statarb.py --refresh  (force re-fetch from Coinbase)
"""

from __future__ import annotations

import argparse

from mds import statarb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--granularity", type=int, default=3600, help="candle size in seconds")
    ap.add_argument("--pages", type=int, default=6, help="history depth (300 candles/page)")
    ap.add_argument("--window", type=int, default=48, help="z-score lookback")
    ap.add_argument("--entry", type=float, default=2.0)
    ap.add_argument("--exit", type=float, default=0.5)
    ap.add_argument("--cost-bps", type=float, default=2.0, help="round-trip cost per unit turnover")
    ap.add_argument("--refresh", action="store_true", help="re-fetch candles from the API")
    args = ap.parse_args()

    r = statarb.run(granularity=args.granularity, pages=args.pages, window=args.window,
                    entry=args.entry, exit=args.exit, cost_bps=args.cost_bps, refresh=args.refresh)
    bt = r["backtest"]

    print("=" * 66)
    print(f"  Stat-arb study: {r['products'][0]} vs {r['products'][1]}")
    print("=" * 66)
    print(f"  observations         : {r['observations']}  ({r['granularity_s']}s candles)")
    print(f"  return correlation   : {r['return_correlation']:.3f}")
    print(f"  hedge ratio (beta)   : {r['hedge_ratio_beta']:.4f}")
    print(f"  Engle-Granger ADF    : {r['adf_stat']:.3f}   (5% crit {r['coint_crit']['5%']})")
    print(f"  cointegrated @ 5%    : {r['cointegrated_5pct']}")
    hl = r["half_life_periods"]
    print(f"  half-life (periods)  : {hl:.1f}" if hl != float("inf") else "  half-life          : inf (no reversion)")
    print("  " + "-" * 62)
    print(f"  net Sharpe (ann.)    : {bt['sharpe']:.2f}")
    print(f"  total return         : {bt['total_return'] * 100:.2f}%")
    print(f"  max drawdown         : {bt['max_drawdown'] * 100:.2f}%")
    print(f"  hit rate             : {bt['hit_rate'] * 100:.1f}%")
    print(f"  trades               : {bt['num_trades']}")
    print("  " + "-" * 62)
    print(f"  VERDICT: {r['verdict']}")
    print("=" * 66)


if __name__ == "__main__":
    main()
