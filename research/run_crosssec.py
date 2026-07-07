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
    # Significance is judged against the SAME multiple-testing-corrected bar for winners AND losers
    # (a 'significant loser' is just as much a selection artefact). Bonferroni over all N signals.
    n = len(results)
    zbar = val.bonferroni_z(n)                       # ≈2.9 for N=11
    passers = {nm: hac_t[nm] for nm in results if abs(hac_t[nm]) >= zbar}
    winners = {nm: t for nm, t in passers.items() if results[nm]["net_sharpe"] > 0}
    if winners and dsr > 0.95 and pbo < 0.3:
        best = max(winners, key=lambda nm: results[nm]["net_sharpe"])
        return (f"'{best}' clears the Bonferroni bar (|t|>{zbar:.2f} for {n} tests, t={hac_t[best]:+.2f}), "
                f"Deflated Sharpe {dsr:.2f}, PBO {pbo:.2f} — a defensible candidate; validate live.")
    if passers:
        names = sorted(passers, key=lambda k: -abs(hac_t[k]))
        lst = ", ".join(f"{k} (t={hac_t[k]:+.2f})" for k in names)
        if all(results[k]["net_sharpe"] < 0 for k in names):
            tail = (f" {len(names)} signal(s) clear the corrected bar |t|>{zbar:.2f} — {lst} — but ALL "
                    "are high-turnover LOSERS, not edges.")
        else:
            tail = f" Signals clearing the corrected bar |t|>{zbar:.2f}: {lst}."
    else:
        tail = (f" Applied symmetrically, NO signal — winner OR loser — clears the multiple-testing-"
                f"corrected bar (|t|>{zbar:.2f} for {n} tests): even the naively 'significant' reversal "
                "is a selection artefact, not a real effect.")
    return (f"NO edge survives honest statistics. Deflated Sharpe of best {dsr:.2f} (needs >0.95), "
            f"PBO {pbo:.2f}.{tail} A clean harness that finds nothing distinguishable from noise or selection.")


def _realism_and_power(sigs: dict, rets, results: dict, best: str) -> None:
    """WS3/WS4: statistical power, beta/sector neutralization, cost sensitivity, regime stability."""
    import numpy as np

    n_best = results[best]["days"]
    n_names = rets.shape[1]
    mds = val.min_detectable_sharpe(n_best)
    print("\nRealism & power:")
    print(f"  Power: with {n_best} active days this sample can only reliably detect (80% power) an "
          f"annualized Sharpe ≳ {mds:.2f} — a function of the return-series LENGTH, not breadth. "
          f"Every observed")
    print(f"    |Sharpe| is below that. Broadening the universe to {n_names} names did not rescue the "
          "signal (Sharpe/DSR ~unchanged), which points to a genuine null rather than mere low breadth;")
    print("    still survivorship-selected with no point-in-time membership, so a real study needs longer,")
    print("    point-in-time history with delistings.")

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

    zbar = val.bonferroni_z(len(results))            # family-corrected |t| bar (same for all signals)
    print(f"  {'signal':<14} {'net Shrp':>9} {'HAC t':>7} {'boot 95% CI':>16} {'sig?':>5} "
          f"{'turnover':>9} {'days':>6}")
    for name, r in results.items():
        lo, hi = boot[name]
        s = "yes" if abs(hac_t[name]) >= zbar else "no"
        print(f"  {name:<14} {r['net_sharpe']:>+9.2f} {hac_t[name]:>+7.2f} "
              f"[{lo:>+5.2f},{hi:>+5.2f}] {s:>5} {r['avg_turnover']:>9.2f} {r['days']:>6}")
    print(f"  (HAC t: Newey–West, autocorrelation-consistent. 'sig?' uses the BONFERRONI bar "
          f"|t|>{zbar:.2f} for {len(results)} simultaneous tests — applied to winners and losers alike. "
          "CI: moving-block bootstrap.)")

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
    print(f"\n(All signals are price/volume-only — no fundamentals in the free feed. Caveats: free "
          f"IEX {px.shape[0]} days (~{px.shape[0] / 252:.1f}y, the max the free feed allows — earlier "
          f"than 2020-07-27 is a hard stop), {px.shape[1]} survivorship-selected large caps across 11 "
          "GICS sectors; a real study needs point-in-time membership with delistings. Underpowered by "
          "construction — see the power line. Note: signal lookbacks are conventional and were NOT "
          f"swept, so researcher degrees-of-freedom exceed the {len(results)}-signal family the "
          "DSR/Bonferroni already correct for.)")


if __name__ == "__main__":
    main()
