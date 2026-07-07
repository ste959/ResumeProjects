"""Cross-sectional equity signal study on the cached Alpaca bars.

Backtests classic cross-sectional signals (12–1 momentum, short-term reversal, low-vol) as
dollar-neutral, unit-gross portfolios with turnover costs, and reports which survive. The point
is the same as the microstructure study: an edge is only real if it clears its trading cost, and
low-turnover signals clear it more easily.

    python run_crosssec.py            # uses cached research/data/equities/bars_1Day.parquet
Ensure the universe is cached first:  python -c "from mds import alpaca_data as a; a.cache_universe()"
"""

from __future__ import annotations

import pandas as pd

from mds import crosssec as xs


def verdict(results: dict[str, dict]) -> str:
    survivors = [n for n, r in results.items() if r["net_sharpe"] > 0]
    if not survivors:
        return "No signal survives costs on this universe/period — an honest negative result."
    best = max(survivors, key=lambda n: results[n]["net_sharpe"])
    r = results[best]
    losers = [n for n, x in results.items() if x["net_sharpe"] <= 0 and x["avg_turnover"] > 0.3]
    note = (f" High-turnover signals ({', '.join(losers)}) are eaten by costs despite any raw edge."
            if losers else "")
    return (f"'{best}' survives costs (net Sharpe {r['net_sharpe']:+.2f}, turnover {r['avg_turnover']:.2f}) "
            f"— low turnover is why.{note} Modest and on a small mega-cap universe, but honest.")


def main() -> None:
    px, rets = xs.returns_panel()
    print(f"Universe: {px.shape[1]} names, {px.shape[0]} days "
          f"({px.index.min().date()} .. {px.index.max().date()})\n")

    sigs = xs.signals(px, rets)
    results = {name: xs.backtest(sig, rets, cost_bps=5.0) for name, sig in sigs.items()}

    print(f"  {'signal':<10} {'gross Shrp':>11} {'net Shrp':>9} {'ann ret':>9} {'max DD':>8} {'turnover':>9}")
    for name, r in results.items():
        print(f"  {name:<10} {r['gross_sharpe']:>+11.2f} {r['net_sharpe']:>+9.2f} "
              f"{r['ann_return']:>+9.1%} {r['max_drawdown']:>+8.1%} {r['avg_turnover']:>9.2f}")

    # P&L correlation — a signal only earns a seat in the portfolio if it DIVERSIFIES the others.
    # This is the number the Phase 6 optimizer actually cares about, not raw signal correlation.
    net = pd.DataFrame({name: r["net"] for name, r in results.items()}).dropna()
    corr = net.corr()
    print("\nNet-P&L correlation (diversification check — near-0 off-diagonal is what we want):")
    print("  " + "".join(f"{c[:8]:>9}" for c in corr.columns))
    for row in corr.index:
        print(f"  {row:<8}" + "".join(f"{corr.loc[row, c]:>+9.2f}" for c in corr.columns))

    print(f"\nVerdict: {verdict(results)}")
    print("\nNote: six signals tested → the best in-sample Sharpe is upward-biased by multiple "
          "testing; treat survivors as candidates, not conclusions. All are price/volume-only "
          "(no fundamentals in the free feed), so no true value/quality factor is present.")
    print("(Caveats: free IEX = ~4.5y history, understated volume, 40 mega-caps only. A real "
          "study needs a far broader universe and point-in-time membership incl. delistings.)")


if __name__ == "__main__":
    main()
