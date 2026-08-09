"""Multi-asset strategic & tactical asset allocation study over real ETF proxies.

Allocates across asset classes (US + intl equities, Treasuries, IG credit, gold, commodities) by
*risk* rather than naive dollars — **risk parity** (equal risk contribution), **min-variance**,
**max-Sharpe**, and a **momentum-tilted tactical overlay** — walk-forward and cost-aware, versus a
static **60/40** benchmark. All performance is measured in **excess of the risk-free rate** (a BIL
T-bill proxy) and reported with the full overfitting-aware gauntlet, downside/tail metrics, a
**regime robustness** breakdown, and a **sensitivity sweep** over the arbitrary design choices.

    python run_assetalloc.py            # fetch (or load cached) ETF bars and run the study
    python run_assetalloc.py --refresh  # re-fetch from Alpaca instead of using the cache

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free paper keys) for the price feed. The allocation math is
pure and unit-tested (tests/test_assetalloc.py); this driver just supplies real data. Deterministic:
the data is cached and every statistic uses a fixed bootstrap seed — see REPRODUCE.md.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import assetalloc as aa

START, END = "2020-07-27", "2026-07-02"          # the max window the free IEX feed provides
RF_PROXY = "BIL"                                  # 1-3m T-bill ETF — its total return ≈ the risk-free rate
CACHE = pathlib.Path(__file__).parent / "data" / "cache" / "assetalloc_bars.parquet"

# Calendar regimes spanning three distinct macro states in the sample.
REGIMES = [
    ("2020-21  zero-rate / recovery", "2020-07-27", "2021-12-31"),
    ("2022     rate shock (stx+bnds)", "2022-01-01", "2022-12-31"),
    ("2023-26  higher-for-longer", "2023-01-01", "2026-07-02"),
]


def _load_prices(refresh: bool) -> pd.DataFrame:
    """Fetch the ETF + risk-free universe, caching to Parquet so reruns are deterministic (REPRODUCE.md)."""
    if CACHE.exists() and not refresh:
        return pd.read_parquet(CACHE)
    syms = list(aa.UNIVERSE) + [RF_PROXY]
    df = ad.fetch_bars(syms, START, END)
    prices = ad.close_panel(df).reindex(columns=syms).dropna()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(CACHE)
    return prices


def main() -> None:
    refresh = "--refresh" in sys.argv
    panel = _load_prices(refresh)
    syms = list(aa.UNIVERSE)
    prices = panel[syms]
    rf = panel[RF_PROXY].pct_change()             # daily risk-free return (BIL total return)

    print(f"Universe ({len(syms)} asset classes): " + ", ".join(f"{s} ({aa.UNIVERSE[s]})" for s in syms))
    print(f"{len(prices)} daily bars, {prices.index[0].date()} → {prices.index[-1].date()}, "
          f"risk-free = {RF_PROXY}, 10 bps cost, monthly rebalance, 1y trailing estimation")
    print("All Sharpes are EXCESS of cash (over 2020-26 the T-bill went ~0% → ~5%).\n")

    s = aa.study(prices, cost_bps=10.0, rf=rf)
    by = {r["method"]: r for r in s["results"]}
    order = ["60/40", "equal", "inverse_vol", "min_variance", "max_sharpe", "risk_parity", "risk_parity_taa"]

    hdr = f"{'strategy':<17}{'ann ret':>9}{'ann vol':>9}{'exSharpe':>9}{'HAC t':>7}{'Sharpe 95% CI':>16}{'max DD':>9}"
    print(hdr); print("-" * len(hdr))
    for m in order:
        r = by[m]
        print(f"{m:<17}{r['ann_return']*100:>8.1f}%{r['ann_vol']*100:>8.1f}%{r['sharpe']:>9.2f}"
              f"{r['hac_t']:>7.1f}   [{r['boot_lo']:>5.2f},{r['boot_hi']:>5.2f}]{r['max_drawdown']*100:>8.1f}%")

    print(f"\n{'DOWNSIDE / TAIL RISK':<17}{'Sortino':>9}{'Calmar':>9}{'CVaR-5%':>10}{'skew':>8}")
    print("-" * 53)
    for m in order:
        r = by[m]
        print(f"{m:<17}{r['sortino']:>9.2f}{r['calmar']:>9.2f}{r['cvar_5']*100:>9.2f}%{r['skew']:>8.2f}")

    g = s["gauntlet"]
    clears = abs(g["best_hac_t"]) >= g["bonferroni_t"]
    powered = g["best_sharpe_ann"] >= g["min_detectable_sharpe"]
    print(f"\nSelection-aware gauntlet ({g['n_strategies']} strategies, {g['n_days']} days — testing several "
          f"allocations on one path IS multiple testing):")
    print(f"  best by exSharpe : {g['best']}  (ann. {g['best_sharpe_ann']}, HAC t {g['best_hac_t']})")
    print(f"  multiple-testing bar |t|>{g['bonferroni_t']}  ->  {'CLEARS' if clears else 'FAILS'}   |   "
          f"Deflated Sharpe {g['deflated_sharpe']} (>0.95)   PBO {g['pbo']} (<0.5)   "
          f"min-detectable {g['min_detectable_sharpe']}  ->  {'powered' if powered else 'UNDERPOWERED'}")

    # --- regime robustness ---
    print("\nRegime robustness (excess Sharpe by sub-period — does the ranking hold?):")
    reg = aa.regime_study(prices, REGIMES, rf=rf)
    rh = f"  {'regime':<32}" + "".join(f"{m[:8]:>9}" for m in order)
    print(rh); print("  " + "-" * (len(rh) - 2))
    for row in reg:
        line = f"  {row['regime']:<32}" + "".join(f"{row['sharpe'].get(m, float('nan')):>9.2f}" for m in order)
        print(line)

    # --- sensitivity sweep ---
    grid = aa.sensitivity(prices, rf=rf)
    winners = pd.Series([g2["winner"] for g2 in grid]).value_counts().to_dict()
    any_clear = sum(g2["clears_bar"] for g2 in grid)
    print(f"\nSensitivity sweep ({len(grid)} configs of lookback×rebalance×cost):")
    print(f"  winner by config: {winners}")
    print(f"  configs where ANYTHING clears the multiple-testing bar: {any_clear}/{len(grid)}")

    ranked = sorted(s["results"], key=lambda r: r["sharpe"], reverse=True)
    win = ranked[0]
    print(f"\nVerdict: best risk-adjusted allocation on this path is **{win['method']}** "
          f"(excess Sharpe {win['sharpe']:.2f}, max DD {win['max_drawdown']*100:.0f}%) — simple diversification "
          f"beating optimized allocation is the DeMiguel 1/N result. But the winner {'clears' if clears else 'does NOT clear'} "
          f"the multiple-testing bar, the ranking {'is' if len(set(winners)) == 1 else 'is NOT'} stable across regimes/parameters, "
          f"and the sample is {'powered' if powered else 'underpowered'}. This is a framework + risk-control demonstration, "
          f"not a statistically established allocation edge; risk parity's real case is regime robustness a single path can't prove.")


if __name__ == "__main__":
    main()
