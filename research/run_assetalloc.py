"""Multi-asset strategic & tactical asset allocation study over real ETF proxies.

Allocates across asset classes (US + intl equities, Treasuries, IG credit, gold, commodities) by
*risk* rather than naive dollars — **risk parity** (equal risk contribution), **min-variance**,
**max-Sharpe**, and a **momentum-tilted tactical overlay** — walk-forward and cost-aware, versus a
static **60/40** benchmark. Reports the same overfitting-aware stats as the rest of the research
(annualized return/vol, Sharpe, Newey–West HAC t, block-bootstrap Sharpe CI, max drawdown).

    python run_assetalloc.py          # fetch ETF daily bars from Alpaca and run the study

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free paper keys) for the price feed. The allocation math is
pure and unit-tested (see tests/test_assetalloc.py); this driver just supplies real data.
"""

from __future__ import annotations

from mds import alpaca_data as ad
from mds import assetalloc as aa

START, END = "2020-07-27", "2026-07-02"          # the max window the free IEX feed provides


def main() -> None:
    syms = list(aa.UNIVERSE)
    df = ad.fetch_bars(syms, START, END)
    prices = ad.close_panel(df).reindex(columns=syms).dropna()
    print(f"Universe ({len(syms)} asset classes): " + ", ".join(f"{s} ({aa.UNIVERSE[s]})" for s in syms))
    print(f"{len(prices)} daily bars, {prices.index[0].date()} → {prices.index[-1].date()}, "
          f"10 bps rebalance cost, monthly rebalance, 1y trailing estimation\n")

    s = aa.study(prices, cost_bps=10.0)
    hdr = f"{'strategy':<17}{'ann ret':>9}{'ann vol':>9}{'Sharpe':>8}{'HAC t':>7}{'Sharpe 95% CI':>16}{'max DD':>9}"
    print(hdr)
    print("-" * len(hdr))
    by = {r["method"]: r for r in s["results"]}
    order = ["60/40", "equal", "inverse_vol", "min_variance", "max_sharpe", "risk_parity", "risk_parity_taa"]
    for m in order:
        r = by[m]
        print(f"{m:<17}{r['ann_return']*100:>8.1f}%{r['ann_vol']*100:>8.1f}%{r['sharpe']:>8.2f}"
              f"{r['hac_t']:>7.1f}   [{r['boot_lo']:>5.2f},{r['boot_hi']:>5.2f}]{r['max_drawdown']*100:>8.1f}%")

    g = s["gauntlet"]
    clears = abs(g["best_hac_t"]) >= g["bonferroni_t"]
    powered = g["best_sharpe_ann"] >= g["min_detectable_sharpe"]
    print(f"\nSelection-aware gauntlet (across {g['n_strategies']} strategies, {g['n_days']} days — "
          f"backtesting several allocations on one path IS multiple testing):")
    print(f"  best by Sharpe : {g['best']}  (ann. Sharpe {g['best_sharpe_ann']}, HAC t {g['best_hac_t']})")
    print(f"  multiple-testing bar : |t| > {g['bonferroni_t']}  ->  {'CLEARS' if clears else 'FAILS'}")
    print(f"  Deflated Sharpe : {g['deflated_sharpe']}  (> 0.95 to be a genuine edge)")
    print(f"  PBO : {g['pbo']}  (< 0.5 is good; prob. the best is overfit)")
    print(f"  min-detectable Sharpe : {g['min_detectable_sharpe']}  ->  "
          f"{'ADEQUATELY POWERED' if powered else 'UNDERPOWERED (too little data to tell)'}")

    ranked = sorted(s["results"], key=lambda r: r["sharpe"], reverse=True)
    win = ranked[0]
    print(f"\nVerdict: on this single ~6-year path the best risk-adjusted allocation was "
          f"**{win['method']}** (Sharpe {win['sharpe']:.2f}, max DD {win['max_drawdown']*100:.0f}%) — a reminder "
          f"that simple diversification frequently beats optimized allocation out-of-sample (the DeMiguel 1/N "
          f"result). But the best strategy {'clears' if clears else 'does NOT clear'} the multiple-testing bar "
          f"and the sample is {'adequately powered' if powered else 'underpowered'}, so this is a framework and "
          f"risk-control demonstration, not a statistically established allocation edge. Risk parity's real case "
          f"is stability and drawdown control across regimes, which one favorable path can't prove.")


if __name__ == "__main__":
    main()
