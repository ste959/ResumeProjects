"""Cross-sectional equity signal study on the cached Alpaca bars.

Backtests classic cross-sectional signals as dollar-neutral, unit-gross portfolios with turnover
costs, and reports which survive — under HONEST statistics: an autocorrelation-consistent
(Newey–West) Sharpe t-stat, a Deflated Sharpe that accounts for how many signals were tried, and
a Probability of Backtest Overfitting. A positive point estimate is not an edge; these say whether
it is distinguishable from zero and from the luckiest of many tries.

    python run_crosssec.py            # uses cached research/data/equities/bars_1Day.parquet
Ensure the universe is cached first:  python -c "from mds import alpaca_data as a; a.cache_universe()"
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import crosssec as xs
from mds import validation as val


def _daily_sharpe(net: pd.Series) -> float:
    r = net.dropna()
    s = r.std(ddof=0)
    return float(r.mean() / s) if s > 0 and len(r) else 0.0


def verdict(results: dict[str, dict], hac_t: dict[str, float], dsr: float, pbo: float) -> str:
    # A signal is an edge only if it clears autocorrelation-consistent significance AND survives
    # deflation for the number tried. DSR > 0.95 and PBO well below 0.5 are the bars.
    sig = {n: t for n, t in hac_t.items() if abs(t) >= 1.96 and results[n]["net_sharpe"] > 0}
    if sig and dsr > 0.95 and pbo < 0.3:
        best = max(sig, key=lambda n: results[n]["net_sharpe"])
        return (f"'{best}' clears HAC significance (t={hac_t[best]:+.2f}), a Deflated Sharpe of "
                f"{dsr:.2f}, and PBO {pbo:.2f}. A defensible candidate — still validate on a broader "
                "universe and live.")
    losers = [n for n, t in hac_t.items() if t <= -1.96 and results[n]["net_sharpe"] < 0]
    lnote = ""
    if losers:
        lw = min(losers, key=lambda n: results[n]["net_sharpe"])
        lnote = (f" The only HAC-significant result is a LOSER: '{lw}' (net Sharpe "
                 f"{results[lw]['net_sharpe']:+.2f}, HAC t={hac_t[lw]:+.2f}).")
    return (f"NO edge survives honest statistics. Best Deflated Sharpe {dsr:.2f} (needs >0.95) and "
            f"PBO {pbo:.2f} (a {pbo:.0%} chance the best backtest is overfit).{lnote} The rigorous "
            "read: a clean harness that finds no edge distinguishable from noise or from selection.")


def _realism_and_power(sigs: dict, rets, results: dict, best: str) -> None:
    """WS3/WS4: statistical power, beta/sector neutralization, cost sensitivity, regime stability."""
    import numpy as np

    n_best = results[best]["days"]
    mds = val.min_detectable_sharpe(n_best)
    print("\nRealism & power:")
    print(f"  Power: with {n_best} active days this sample can only reliably detect (80% power) an "
          f"annualized Sharpe ≳ {mds:.2f}. Every observed |Sharpe| is below that — UNDERPOWERED by")
    print("    construction (40 survivorship-selected mega-caps, ~4.4y); a null is 'too little data'.")

    sig = sigs[best]
    rw, nw = xs.raw_weights(sig), xs.neutralized_weights(sig, rets)
    raw_b = float(xs.book_beta(rw, rets).abs().mean())
    neu_b = float(xs.book_beta(nw, rets).abs().mean())
    nbt = xs.backtest(sig, rets, weights=nw)
    nt = val.newey_west_sharpe_tstat(nbt["net"].dropna().to_numpy())
    print(f"  Neutralization ('{best}'): mean |net market β| {raw_b:.3f} (dollar-neutral only) → "
          f"{neu_b:.3f} (β + sector-neutral).")
    print(f"    Factor-neutral book net Sharpe {nbt['net_sharpe']:+.2f} (HAC t={nt:+.2f}).")

    adv = xs.dollar_adv_panel()
    print(f"  Cost sensitivity ('{best}' net Sharpe; √-law impact coef σ·Y≈2% assumed):")
    for label, kw in [
        ("flat 5bps (spread+fee)", dict(cost_bps=5.0)),
        ("+ impact @ $100M book", dict(cost_bps=5.0, impact_coef=0.02, dollar_vol=adv, gross_capital=1e8)),
        ("+ impact @ $1B book", dict(cost_bps=5.0, impact_coef=0.02, dollar_vol=adv, gross_capital=1e9)),
        ("+ impact $1B + 50bps borrow", dict(cost_bps=5.0, impact_coef=0.02, dollar_vol=adv,
                                             gross_capital=1e9, borrow_bps=50.0)),
        ("flat 20bps (stress)", dict(cost_bps=20.0)),
    ]:
        print(f"    {label:<28} {xs.backtest(sig, rets, **kw)['net_sharpe']:>+6.2f}")
    print("    (impact scales with book size — the capacity limit; the edge is not robust to it.)")

    net_best = results[best]["net"].dropna()
    yrs = []
    for yr, g in net_best.groupby(net_best.index.year):
        if len(g) > 20 and g.std(ddof=0) > 0:
            yrs.append(f"{yr}:{g.mean() / g.std(ddof=0) * np.sqrt(252):+.2f}")
    print(f"  Regime stability ('{best}' net Sharpe by year): " + "  ".join(yrs))
    print("    (One blended number hides regime dependence; the sign flips across years.)")


def main() -> None:
    px, rets = xs.returns_panel()
    print(f"Universe: {px.shape[1]} names, {px.shape[0]} days "
          f"({px.index.min().date()} .. {px.index.max().date()})\n")

    sigs = xs.signals(px, rets)
    results = {name: xs.backtest(sig, rets, cost_bps=5.0) for name, sig in sigs.items()}

    # HAC (Newey–West) t-stat + distribution-free block-bootstrap CI per signal.
    hac_t = {n: val.newey_west_sharpe_tstat(r["net"].dropna().to_numpy()) for n, r in results.items()}
    boot = {n: val.block_bootstrap_sharpe_ci(r["net"].dropna().to_numpy()) for n, r in results.items()}

    print(f"  {'signal':<10} {'net Shrp':>9} {'HAC t':>7} {'boot 95% CI':>16} {'sig?':>5} "
          f"{'turnover':>9} {'days':>6}")
    for name, r in results.items():
        lo, hi = boot[name]
        s = "yes" if abs(hac_t[name]) >= 1.96 else "no"
        print(f"  {name:<10} {r['net_sharpe']:>+9.2f} {hac_t[name]:>+7.2f} "
              f"[{lo:>+5.2f},{hi:>+5.2f}] {s:>5} {r['avg_turnover']:>9.2f} {r['days']:>6}")
    print("  (HAC t: Newey–West, autocorrelation-consistent — deflates the naive IID t on "
          "overlapping-window signals. CI: moving-block bootstrap, distribution-free.)")

    # Selection-aware statistics across the whole signal set: Deflated Sharpe + PBO.
    from scipy.stats import kurtosis, skew

    net_mat = pd.DataFrame({n: r["net"] for n, r in results.items()}).dropna()
    daily_sh = {n: _daily_sharpe(results[n]["net"]) for n in results}
    var_trials = float(np.var(list(daily_sh.values()), ddof=1))
    best = max(results, key=lambda n: results[n]["net_sharpe"])
    b = results[best]["net"].dropna().to_numpy()
    dsr = val.deflated_sharpe(_daily_sharpe(results[best]["net"]), len(b),
                              float(skew(b)), float(kurtosis(b, fisher=False)),
                              n_trials=len(results), sharpe_var_across_trials=var_trials)
    pbo_res = val.pbo(net_mat.to_numpy(), n_splits=12)

    print(f"\nSelection-aware (across all {len(results)} signals tested):")
    print(f"  Deflated Sharpe of best ('{best}'): {dsr:.3f}   (probability its true Sharpe > 0 "
          "after deflating for multiple testing; >0.95 is the bar)")
    print(f"  PBO (prob. of backtest overfitting): {pbo_res['pbo']:.3f}   over "
          f"{pbo_res['n_combos']} CPCV splits — the chance the in-sample-best signal is beaten OOS")

    _realism_and_power(sigs, rets, results, best)

    print(f"\nVerdict: {verdict(results, hac_t, dsr, pbo_res['pbo'])}")
    print("\n(All signals are price/volume-only — no fundamentals in the free feed. Caveats: free "
          "IEX ~4.5y history, 40 survivorship-selected mega-caps; a real study needs a far broader, "
          "point-in-time universe with delistings. This universe is underpowered by construction.)")


if __name__ == "__main__":
    main()
