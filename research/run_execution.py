"""Execution realism & capacity — does the edge survive real trading costs and real size?

Prices the same strategies two ways: a naive **flat 10 bps**, and a **realistic** model (Corwin–Schultz
spread + square-root market impact + a participation cap with partial fills + short-borrow/financing),
using ADV, volatility, and spread estimated from real OHLCV. Then it sweeps **AUM** to show the capacity
curve — the point at which a strategy's own trades move the market enough to eat the alpha.

    python run_execution.py            # fetch (or load cached) OHLCV, run flat vs realistic + capacity
    python run_execution.py --refresh  # re-fetch from Alpaca

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys). The models are pure and unit-tested
(tests/test_execution.py); this driver supplies real data.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import engine as eng
from mds import execution as ex
from mds import strategies_lib as sl
from mds import trend as tr

START, END = "2020-07-27", "2026-07-02"
RF_PROXY = "BIL"
CACHE = pathlib.Path(__file__).parent / "data" / "cache"
# The free IEX feed reports only IEX's own share of consolidated volume (~4%). Scale it up to approximate
# true ADV, so the capacity thresholds are in realistic dollars (else they'd bind ~25× too early). A
# documented approximation — a paid consolidated feed would remove the guess.
IEX_VOLUME_SHARE = 0.04


def _load(refresh: bool):
    """OHLCV panels for the universe + the daily risk-free. Cached for determinism."""
    syms = list(tr.UNIVERSE) + [RF_PROXY]
    paths = {f: CACHE / f"exec_{f}.parquet" for f in ("close", "high", "low", "volume")}
    if all(p.exists() for p in paths.values()) and not refresh:
        panels = {f: pd.read_parquet(p) for f, p in paths.items()}
    else:
        df = ad.fetch_bars(syms, START, END, adjustment="all")
        panels = {f: ad.close_panel(df, f).reindex(columns=syms).dropna() for f in paths}
        CACHE.mkdir(parents=True, exist_ok=True)
        for f, p in paths.items():
            panels[f].to_parquet(p)
    rf = panels["close"][RF_PROXY].pct_change()
    u = list(tr.UNIVERSE)
    return {f: panels[f][u] for f in panels}, rf


def main() -> None:
    px, rf = _load("--refresh" in sys.argv)
    close = px["close"]
    consolidated_volume = px["volume"] / IEX_VOLUME_SHARE          # approximate true (consolidated) ADV
    liq = ex.estimate_liquidity(close, consolidated_volume, px["high"], px["low"])   # ADV-based spread (default)
    syms = list(tr.UNIVERSE)

    spread_bps = (liq.spread_frac.iloc[-1] * 1e4).round(1)
    print(f"Execution realism · {len(syms)} markets · {close.index[0].date()} → {close.index[-1].date()}")
    print(f"ADV-based spreads (bps, latest): " +
          ", ".join(f"{s} {spread_bps[s]:.1f}" for s in syms[:8]) + " …")
    print("(Corwin–Schultz high/low spread is also implemented, as a cross-check — it overestimates for "
          "liquid names, so the ADV-tier model is the default.)\n")

    strategies = [sl.RiskParity(syms), sl.TimeSeriesMomentum(syms)]

    print(f"{'strategy':<16}{'flat exSharpe':>15}{'realistic exSharpe':>20}{'Δ':>8}   (AUM $100M)")
    print("-" * 60)
    for s in strategies:
        flat = eng.run(s, close, eng.BacktestConfig(cost_bps=10.0, rf=rf))
        real = eng.run(s, close, eng.BacktestConfig(execution=ex.RealisticExecution(), aum=1e8, rf=rf), liq)
        print(f"{s.name:<16}{flat.stats['sharpe']:>15.2f}{real.stats['sharpe']:>20.2f}"
              f"{real.stats['sharpe']-flat.stats['sharpe']:>+8.2f}")

    # Capacity curve on the trend book — highest turnover + trades the thinner sleeves.
    print(f"\nCapacity curve — ts-momentum under realistic execution (edge vs. size):")
    print(f"  {'AUM':>8}{'exSharpe':>10}{'ann ret':>9}{'turnover':>10}{'avg gross':>11}")
    aums = [1e8, 5e8, 1e9, 5e9, 2e10, 5e10]
    curve = eng.capacity_curve(sl.TimeSeriesMomentum(syms), close, liq, aums,
                               base=eng.BacktestConfig(rf=rf))
    for row, aum in zip(curve, aums):
        label = f"${aum/1e6:.0f}M" if aum < 1e9 else f"${aum/1e9:.0f}B"
        print(f"  {label:>8}{row['sharpe']:>10.2f}{row['ann_return']*100:>8.1f}%{row['turnover_ann']:>9.0f}x"
              f"{row['avg_gross']:>10.2f}x")

    first, last = curve[0], curve[-1]
    print(f"\nVerdict: realistic costs move the ranking (a flat-bps backtest flatters high-turnover books). "
          f"On the capacity curve the trend book's excess Sharpe goes {first['sharpe']:.2f} → "
          f"{last['sharpe']:.2f} from ${aums[0]/1e6:.0f}M to ${aums[-1]/1e9:.0f}B as its trades become a "
          f"large share of ADV and can no longer fill — the average gross book shrinks from "
          f"{first['avg_gross']:.2f}x to {last['avg_gross']:.2f}x (throttled by the participation cap). An "
          f"'alpha' that runs at $100M is a different claim than one that runs at $50B; the honest platform "
          f"makes the capacity ceiling visible instead of assuming size is free.")


if __name__ == "__main__":
    main()
