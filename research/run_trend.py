"""Enhanced multi-asset trend-following study over real ETF proxies.

Builds a diversified time-series-momentum book and adds one enhancement at a time — vol-targeting,
a multi-timescale risk-adjusted signal, a portfolio vol overlay, a **carry** blend, crash-protection,
and a cross-sectional momentum overlay — running an **ablation** so each knob's contribution is visible.
Everything is walk-forward and cost-aware, measured in **excess of cash** (BIL), and judged by the same
overfitting-aware gauntlet, regime breakdown, sensitivity sweep, and tail metrics as the allocation study.

    python run_trend.py            # fetch (or load cached) ETF bars and run the study
    python run_trend.py --refresh  # re-fetch from Alpaca instead of using the cache

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys) for the price feed. Two panels are fetched: total-
return (dividend-adjusted) and price-only (split-adjusted) — the gap is the carry (income-yield) signal.
The trend math is pure and unit-tested (tests/test_trend.py); this driver just supplies real data.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import evaluation as ev
from mds import trend as tr

START, END = "2020-07-27", "2026-07-02"          # the max window the free IEX feed provides
RF_PROXY = "BIL"                                  # 1-3m T-bill ETF — its total return ≈ the risk-free rate
CACHE = pathlib.Path(__file__).parent / "data" / "cache"

REGIMES = [
    ("2020-21  zero-rate / recovery", "2020-07-27", "2021-12-31"),
    ("2022     rate shock (stx+bnds)", "2022-01-01", "2022-12-31"),
    ("2023-26  higher-for-longer", "2023-01-01", "2026-07-02"),
]


def _load(refresh: bool) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Return (total-return panel, price-only panel, daily risk-free). Cached to Parquet for determinism.
    Total-return uses split+dividend adjustment; price-only uses split-only — their gap is the carry."""
    tot_c, px_c = CACHE / "trend_total.parquet", CACHE / "trend_price.parquet"
    syms = list(tr.UNIVERSE) + [RF_PROXY]
    if tot_c.exists() and px_c.exists() and not refresh:
        total, price = pd.read_parquet(tot_c), pd.read_parquet(px_c)
    else:
        total = ad.close_panel(ad.fetch_bars(syms, START, END, adjustment="all")).reindex(columns=syms).dropna()
        price = ad.close_panel(ad.fetch_bars(syms, START, END, adjustment="split")).reindex(columns=syms)
        price = price.reindex(total.index)           # align price-only to the total-return calendar
        CACHE.mkdir(parents=True, exist_ok=True)
        total.to_parquet(tot_c); price.to_parquet(px_c)
    rf = total[RF_PROXY].pct_change()
    return total, price, rf


def main() -> None:
    total, price, rf = _load("--refresh" in sys.argv)
    syms = list(tr.UNIVERSE)
    tp, pp = total[syms], price[syms]                # total-return drives P&L; price-only feeds carry

    print(f"Universe ({len(syms)} markets): " + ", ".join(f"{s}({tr.UNIVERSE[s]})" for s in syms))
    print(f"{len(tp)} daily bars, {tp.index[0].date()} → {tp.index[-1].date()}, "
          f"risk-free = {RF_PROXY}, 10 bps cost, monthly rebalance, 10% vol target")
    print("All Sharpes are EXCESS of cash. Trend captures a *premium*; the question is what the "
          "enhancements add on top.\n")

    ab = tr.ablation(tp, pp, rf=rf)

    hdr = f"{'ablation stage':<26}{'ann ret':>9}{'ann vol':>9}{'exSharpe':>9}{'HAC t':>7}{'max DD':>9}{'Sortino':>9}{'skew':>7}"
    print(hdr); print("-" * len(hdr))
    for r in ab["stages"]:
        print(f"{r['stage']:<26}{r['ann_return']*100:>8.1f}%{r['ann_vol']*100:>8.1f}%{r['sharpe']:>9.2f}"
              f"{r['hac_t']:>7.1f}{r['max_drawdown']*100:>8.1f}%{r['sortino']:>9.2f}{r['skew']:>7.2f}")

    g = ab["gauntlet"]
    clears = abs(g["best_hac_t"]) >= g["bonferroni_t"]
    powered = g["best_sharpe_ann"] >= g["min_detectable_sharpe"]
    print(f"\nSelection-aware gauntlet ({g['n_strategies']} ablation variants, {g['n_days']} days — "
          f"trying several builds on one path IS multiple testing):")
    print(f"  best by exSharpe : {g['best']}  (ann. {g['best_sharpe_ann']}, HAC t {g['best_hac_t']})")
    print(f"  multiple-testing bar |t|>{g['bonferroni_t']}  ->  {'CLEARS' if clears else 'FAILS'}   |   "
          f"Deflated Sharpe {g['deflated_sharpe']} (>0.95)   PBO {g['pbo']} (<0.5)   "
          f"min-detectable {g['min_detectable_sharpe']}  ->  {'powered' if powered else 'UNDERPOWERED'}")

    print("\nRegime robustness of the full system (excess Sharpe / max DD by sub-period):")
    reg = tr.regime_study(tp, REGIMES, pp, rf=rf)
    for row in reg:
        print(f"  {row['regime']:<32} Sharpe {row['sharpe']:>6.2f}   max DD {row['max_drawdown']*100:>6.1f}%")

    grid = tr.sensitivity(tp, pp, rf=rf)
    pos = sum(row["sharpe"] > 0 for row in grid)
    sig = sum(abs(row["hac_t"]) >= 1.96 for row in grid)
    sh = pd.Series([row["sharpe"] for row in grid])
    print(f"\nSensitivity sweep ({len(grid)} configs of rebalance×cost×vol-target):")
    print(f"  full-system exSharpe range [{sh.min():.2f}, {sh.max():.2f}], median {sh.median():.2f}")
    print(f"  configs with positive Sharpe: {pos}/{len(grid)}   |   with |HAC t|≥1.96: {sig}/{len(grid)}")

    # ── Diagnostics: attribute the numbers instead of just reporting them ──────────────────────────
    stages, nets = ab["stages"], ab["nets"]
    print("\n" + "=" * 78 + "\nDIAGNOSTICS — what is actually happening\n" + "=" * 78)

    print("\n[1] Vol-target decomposition (signal fixed) — attributing the big ablation jump:")
    decomp = tr.voltarget_decomposition(tp, pp, rf=rf)
    for d in decomp:
        print(f"  {d['label']:<40} exSharpe {d['sharpe']:>6.2f}   ann vol {d['ann_vol']*100:>5.1f}%   "
              f"avg gross {d['avg_gross']:>4.2f}x")

    print("\n[2] Leave-one-out (remove ONE enhancement from the full system; Δ vs full):")
    loo = tr.loo_ablation(tp, pp, rf=rf)
    loo_carry = next(r for r in loo if r["removed"] == "carry")
    for r in loo:
        tag = "" if r["removed"] == "—" else ("  helps" if r["delta"] < 0 else "  HURTS" if r["delta"] > 0 else "  neutral")
        print(f"  {r['variant']:<20} exSharpe {r['sharpe']:>6.2f}   Δ {r['delta']:>+6.3f}{tag}")

    print("\n[3] Sleeve attribution of the full system (which markets drove the P&L):")
    at = tr.attribution(tp, pp, rf=rf, regimes=REGIMES)
    print(f"  avg gross {at['avg_gross']:.2f}x, annual turnover ~{at['turnover_ann']:.0f}x")
    print("  net exposure (avg signed weight):  " +
          "  ".join(f"{k} {v:+.2f}" for k, v in at["net_exposure"].items()))
    print("  total P&L contribution by sleeve:  " +
          "  ".join(f"{k} {v*100:+.1f}%" for k, v in at["per_sleeve"].items()))
    crisis_attr = at["regime_sleeve"].get(next(k for k in at["regime_sleeve"] if "2022" in k))
    print("  2022 P&L by sleeve:                " +
          "  ".join(f"{k} {v*100:+.1f}%" for k, v in crisis_attr.items()))

    print("\n[4] Are the ablation gains real? Paired block-bootstrap of the Sharpe DIFFERENCE:")
    peak_stage = max(stages, key=lambda r: r["sharpe"])["stage"]
    pv_paired = None
    for a_name, b_name, desc in [(peak_stage, stages[0]["stage"], "peak vs vanilla"),
                                 (stages[-1]["stage"], peak_stage, "full vs peak")]:
        d = ev.paired_sharpe_diff_ci(nets[a_name], nets[b_name], rf=rf)
        if desc == "peak vs vanilla":
            pv_paired = d
        real = "distinguishable" if (d["lo"] > 0 or d["hi"] < 0) else "NOT distinguishable from 0"
        print(f"  {desc:<16} ΔSharpe {d['diff']:>+6.2f}  95% CI [{d['lo']:>+5.2f}, {d['hi']:>+5.2f}]  → {real}")

    print("\n[5] Factor exposure — is the 'premium' just disguised beta?")
    fac = pd.DataFrame({"eq(SPY)": tp["SPY"].pct_change(), "dur(TLT)": tp["TLT"].pct_change()}).dropna()
    full_net = nets[stages[-1]["stage"]]
    fb = tr.factor_betas(full_net, fac, rf=rf)
    fb22 = tr.factor_betas(full_net.loc["2022-01-01":"2022-12-31"], fac, rf=rf)
    print(f"  full sample: alpha {fb['alpha_ann']*100:+.1f}%/yr (t {fb['alpha_t']:+.1f}), "
          f"β_eq {fb['betas']['eq(SPY)']:+.2f} (t {fb['beta_t']['eq(SPY)']:+.1f}), "
          f"β_dur {fb['betas']['dur(TLT)']:+.2f} (t {fb['beta_t']['dur(TLT)']:+.1f}), R² {fb['r2']:.2f}")
    print(f"  2022 only:   β_eq {fb22['betas']['eq(SPY)']:+.2f}, β_dur {fb22['betas']['dur(TLT)']:+.2f}  "
          f"(crisis convexity should show as LOW/negative duration beta, not a static short)")

    sig_only, timing = decomp[0]["sharpe"], decomp[1]["sharpe"]
    dur_b, dur_t = fb["betas"]["dur(TLT)"], fb["beta_t"]["dur(TLT)"]
    print(f"\nVerdict (revised BY the diagnostics — this is the point of running them):")
    print(f"  • It isn't the trend signal. Constant-gross, the signal alone Sharpes {sig_only:.2f}; nearly all "
          f"of the {decomp[2]['sharpe']:.2f} comes from **volatility-timing** (scaling exposure by inverse vol "
          f"over time — a Moreira–Muir effect), with correlation-aware sizing adding a little.")
    print(f"  • Carry is a real detractor, not an ordering artifact: leave-one-out shows removing it LIFTS the "
          f"full system {stages[-1]['sharpe']:.2f} → {loo_carry['sharpe']:.2f}.")
    print(f"  • None of it is statistically established: peak-vs-vanilla ΔSharpe {pv_paired['diff']:+.2f} has a "
          f"95% CI [{pv_paired['lo']:+.2f}, {pv_paired['hi']:+.2f}] — indistinguishable from noise; nothing "
          f"clears the multiple-testing bar; the sample is underpowered.")
    print(f"  • The '2022 crisis convexity' is largely a factor bet: the book is equity-neutral (β_eq≈0) but "
          f"carries a big, highly-significant **short-duration beta {dur_b:+.2f} (t {dur_t:+.1f})**, and the "
          f"sleeve attribution shows 2022 was short credit/rates + long commodities/dollar — a *static* "
          f"short-bond tilt cashing in during a bond bear market, more than pure convexity.")
    print(f"  Honest bottom line: what looks like 'enhanced trend alpha' is mostly **vol-timing plus a "
          f"short-duration factor tilt** — a useful, equity-neutral, diversifying return stream, but not "
          f"signal-driven alpha and not statistically proven on ~6 years. The diagnostics turned a murky "
          f"Sharpe into a mechanism you can name, argue with, and size honestly.")


if __name__ == "__main__":
    main()
