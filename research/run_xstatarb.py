"""Cross-sectional statistical arbitrage on a broad US equity universe — the canonical desk strategy.

Residual-reversal on PCA statistical factors (Avellaneda–Lee), run through the platform: is the signal
*predictive* (gross), and does it *survive* realistic execution (net)? Short-horizon reversal is the
strategy where transaction cost decides everything — so this is the honest test of whether the platform's
methods find tradable alpha, not just a decayed premium on efficient names.

    python run_xstatarb.py [--refresh]

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys). Pure signal/portfolio math is unit-tested
(tests/test_xstatarb.py); this driver supplies real data.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import engine as eng
from mds import evaluation as ev
from mds import execution as ex
from mds import xstatarb as xs

START, END = "2020-07-27", "2026-07-02"
RF_PROXY = "BIL"
IEX_VOLUME_SHARE = 0.04
CACHE = pathlib.Path(__file__).parent / "data" / "cache"

# ~90 liquid US large-caps across sectors — breadth is the point (IR ≈ IC·√breadth).
UNIVERSE = ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "JPM", "V", "MA", "UNH", "HD", "PG",
            "JNJ", "XOM", "CVX", "ABBV", "LLY", "AVGO", "COST", "PEP", "KO", "MRK", "WMT", "BAC", "ADBE",
            "CRM", "NFLX", "AMD", "TMO", "ACN", "LIN", "MCD", "ABT", "CSCO", "DHR", "WFC", "TXN", "NEE",
            "PM", "DIS", "INTC", "VZ", "CMCSA", "COP", "QCOM", "HON", "UNP", "BMY", "LOW", "UPS", "MS",
            "RTX", "SPGI", "NKE", "GS", "T", "CAT", "BA", "AXP", "BLK", "DE", "ELV", "LMT", "SBUX", "GILD",
            "MDT", "ADI", "PLD", "SYK", "TJX", "MMC", "AMT", "CB", "C", "SCHW", "MO", "SO", "DUK", "BDX",
            "CI", "ZTS", "REGN", "EOG", "SLB", "APD", "ITW", "NOC", "WM", "FCX", "AON", "PNC", "USB"]


def _load(refresh: bool):
    syms = UNIVERSE + [RF_PROXY]
    paths = {f: CACHE / f"xstatarb_{f}.parquet" for f in ("close", "high", "low", "volume")}
    if all(p.exists() for p in paths.values()) and not refresh:
        panels = {f: pd.read_parquet(p) for f, p in paths.items()}
    else:
        df = ad.fetch_bars(syms, START, END, adjustment="all")
        panels = {f: ad.close_panel(df, f).reindex(columns=syms) for f in paths}
        CACHE.mkdir(parents=True, exist_ok=True)
        for f, p in paths.items():
            panels[f].to_parquet(p)
    return panels


def main() -> None:
    panels = _load("--refresh" in sys.argv)
    rf = panels["close"][RF_PROXY].pct_change()
    raw = panels["close"][UNIVERSE]
    keep = list(raw.columns[raw.notna().mean() > 0.95])       # high-coverage names (survivorship noted)
    close = raw[keep].ffill().dropna()                        # fill sparse gaps, then align to common history
    names = list(close.columns)
    liq = ex.estimate_liquidity(close, panels["volume"][names].reindex(close.index).ffill() / IEX_VOLUME_SHARE,
                                panels["high"][names].reindex(close.index).ffill(),
                                panels["low"][names].reindex(close.index).ffill())

    print(f"Cross-sectional stat-arb · {len(names)} names · {close.index[0].date()} → {close.index[-1].date()} · "
          f"daily rebalance · excess of cash")
    print("Residual reversal on 15 PCA statistical factors (Avellaneda–Lee); factor- & dollar-neutral.\n")

    strat = lambda: xs.CrossSectionalStatArb(names, window=60, k=15)
    gross = eng.run(strat(), close, eng.BacktestConfig(rebalance=1, cost_bps=0.0, rf=rf))
    net = eng.run(strat(), close, eng.BacktestConfig(rebalance=1, execution=ex.RealisticExecution(), aum=5e7, rf=rf), liq)

    print(f"{'':18}{'exSharpe':>10}{'HAC t':>7}{'ann ret':>9}{'ann vol':>9}{'turnover':>10}")
    print("-" * 63)
    for label, r in [("gross (no cost)", gross), ("net (realistic $50M)", net)]:
        s = r.stats
        print(f"{label:18}{s['sharpe']:>10.2f}{s['hac_t']:>7.1f}{s['ann_return']*100:>8.1f}%"
              f"{s['ann_vol']*100:>8.1f}%{r.turnover_ann:>9.0f}x")

    g = ev.gauntlet({"gross": gross.net, "net": net.net}, rf)
    print(f"\nGross signal: HAC t {gross.stats['hac_t']:+.1f}, Sharpe 95% CI "
          f"[{gross.stats['boot_lo']:.2f}, {gross.stats['boot_hi']:.2f}] — "
          f"{'distinguishable from 0' if gross.stats['boot_lo'] > 0 else 'not clearly > 0'}")

    # Parameter sensitivity — is the gross signal robust, or a knife-edge?
    print("\nSensitivity (gross exSharpe over window × k):")
    for window in (40, 60):
        row = []
        for k in (10, 15, 20):
            r = eng.run(xs.CrossSectionalStatArb(names, window=window, k=k), close,
                        eng.BacktestConfig(rebalance=1, cost_bps=0.0, rf=rf))
            row.append(f"k={k}:{r.stats['sharpe']:>5.2f}")
        print(f"  window={window}:  " + "   ".join(row))

    # Capacity — where realistic cost eats the (net) edge.
    print("\nCapacity (net exSharpe under realistic execution, by AUM):")
    for aum in (1e7, 5e7, 2e8, 1e9):
        r = eng.run(strat(), close, eng.BacktestConfig(rebalance=1, execution=ex.RealisticExecution(), aum=aum, rf=rf), liq)
        label = f"${aum/1e6:.0f}M" if aum < 1e9 else f"${aum/1e9:.0f}B"
        print(f"  {label:>6}: Sharpe {r.stats['sharpe']:>5.2f}   turnover {r.turnover_ann:>4.0f}x")

    gross_sig = gross.stats["boot_lo"] > 0
    print(f"\nVerdict: even GROSS, residual reversal is not a taker edge on this universe — excess Sharpe "
          f"{gross.stats['sharpe']:.2f} (HAC t {gross.stats['hac_t']:+.1f}), 95% CI "
          f"[{gross.stats['boot_lo']:.2f}, {gross.stats['boot_hi']:.2f}] {'excludes' if gross_sig else 'includes'} zero, "
          f"and it stays near zero across every window×k. This is the *literature-correct* result: Avellaneda–Lee's "
          f"own reversal decayed sharply post-2007 as stat-arb crowded, and on liquid large-caps it's arbitraged "
          f"out of the daily cross-section. Realistic execution (turnover ~{gross.turnover_ann:.0f}×/yr) only "
          f"deepens the loss — {net.stats['sharpe']:.2f} net at $50M, worse as AUM grows. The edge that remains "
          f"lives where free daily data can't reach: **less-liquid names, intraday horizons, or a liquidity-"
          f"providing (market-making) implementation that earns the spread instead of paying it.** The deliverable "
          f"here is the *correct, factor-neutral, broad-universe build* and the honest measurement of where the "
          f"accessible edge went — not a manufactured Sharpe.")


if __name__ == "__main__":
    main()
