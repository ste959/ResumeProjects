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
from mds.stats import sharpe_ci, sharpe_tstat


def verdict(results: dict[str, dict]) -> str:
    # A positive net Sharpe is not an edge unless it is statistically distinguishable from zero.
    # With ~4.4y of daily data a Sharpe needs |t| ≳ 2 (95% CI excluding 0) to clear that bar.
    sig = {n: sharpe_tstat(r["net_sharpe"], r["days"]) for n, r in results.items()}
    significant = {n: t for n, t in sig.items() if abs(t) >= 1.96}
    winners = {n: t for n, t in significant.items() if results[n]["net_sharpe"] > 0}
    if winners:
        best = max(winners, key=lambda n: results[n]["net_sharpe"])
        r = results[best]
        return (f"'{best}' is a statistically significant survivor (net Sharpe {r['net_sharpe']:+.2f}, "
                f"t={sig[best]:+.2f}). Still validate OOS and on a broader universe.")
    # Report the honest headline: nothing clears significance.
    best = max(results, key=lambda n: results[n]["net_sharpe"])
    r, tb = results[best], sig[best]
    lo, hi = sharpe_ci(r["net_sharpe"], r["days"])
    losers = [n for n, t in significant.items() if results[n]["net_sharpe"] < 0]
    loser_note = ""
    if losers:
        lworst = min(losers, key=lambda n: results[n]["net_sharpe"])
        loser_note = (f" The ONLY statistically significant result is a LOSER: '{lworst}' "
                      f"(net Sharpe {results[lworst]['net_sharpe']:+.2f}, t={sig[lworst]:+.2f}).")
    return ("NO edge survives statistical significance. The best signal, "
            f"'{best}' (net Sharpe {r['net_sharpe']:+.2f}, t={tb:+.2f}, 95% CI [{lo:+.2f}, {hi:+.2f}]), "
            "has a confidence interval that straddles 0 — not distinguishable from zero at this "
            f"sample size.{loser_note} The rigorous read: a clean harness that finds no real edge.")


def main() -> None:
    px, rets = xs.returns_panel()
    print(f"Universe: {px.shape[1]} names, {px.shape[0]} days "
          f"({px.index.min().date()} .. {px.index.max().date()})\n")

    sigs = xs.signals(px, rets)
    results = {name: xs.backtest(sig, rets, cost_bps=5.0) for name, sig in sigs.items()}

    print(f"  {'signal':<10} {'net Shrp':>9} {'t-stat':>7} {'95% CI':>16} {'sig?':>5} "
          f"{'ann ret':>9} {'turnover':>9} {'days':>6}")
    for name, r in results.items():
        t = sharpe_tstat(r["net_sharpe"], r["days"])
        lo, hi = sharpe_ci(r["net_sharpe"], r["days"])
        sig = "yes" if abs(t) >= 1.96 else "no"
        print(f"  {name:<10} {r['net_sharpe']:>+9.2f} {t:>+7.2f} "
              f"[{lo:>+5.2f},{hi:>+5.2f}] {sig:>5} "
              f"{r['ann_return']:>+9.1%} {r['avg_turnover']:>9.2f} {r['days']:>6}")
    print("  (t-stat/CI: large-sample SE for an annualized Sharpe; |t|>~2 ⇒ 95% CI excludes 0.)")

    # P&L correlation — a signal only earns a seat in the portfolio if it DIVERSIFIES the others.
    # This is the number the Phase 6 optimizer actually cares about, not raw signal correlation.
    net = pd.DataFrame({name: r["net"] for name, r in results.items()}).dropna()
    corr = net.corr()
    print("\nNet-P&L correlation (diversification check — near-0 off-diagonal is what we want):")
    print("  " + "".join(f"{c[:8]:>9}" for c in corr.columns))
    for row in corr.index:
        print(f"  {row:<8}" + "".join(f"{corr.loc[row, c]:>+9.2f}" for c in corr.columns))

    print(f"\nVerdict: {verdict(results)}")
    print("\nMultiple-testing caveat: six signals tested → the best-of-6 in-sample Sharpe is "
          "upward-biased by selection; a deflated/Bonferroni view (α/6 ⇒ ~|t|>2.6) raises the "
          "significance bar even further, so a marginal single-test result would fail outright. "
          "All signals are price/volume-only (no fundamentals in the free feed).")
    print("(Caveats: free IEX = ~4.5y history, understated volume, 40 mega-caps only. A real "
          "study needs a far broader universe and point-in-time membership incl. delistings.)")


if __name__ == "__main__":
    main()
