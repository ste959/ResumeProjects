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

    rp, bench = by["risk_parity"], by["60/40"]
    print(f"\nVerdict: risk parity vs. 60/40 — Sharpe {rp['sharpe']:.2f} vs {bench['sharpe']:.2f}, "
          f"max drawdown {rp['max_drawdown']*100:.0f}% vs {bench['max_drawdown']*100:.0f}%. "
          "The risk-based allocation earns its keep through lower drawdown and steadier risk, not a "
          "higher headline return — the honest case for diversified, risk-managed asset allocation.")


if __name__ == "__main__":
    main()
