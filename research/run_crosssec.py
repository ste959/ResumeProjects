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

    print(f"\nVerdict: {verdict(results, hac_t, dsr, pbo_res['pbo'])}")
    print("\n(All signals are price/volume-only — no fundamentals in the free feed. Caveats: free "
          "IEX ~4.5y history, 40 survivorship-selected mega-caps; a real study needs a far broader, "
          "point-in-time universe with delistings. This universe is underpowered by construction.)")


if __name__ == "__main__":
    main()
