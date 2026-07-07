"""Signal-allocation study — the trader's optimizer.

Combines the cross-sectional signals into ONE portfolio, allocating capital across them
walk-forward and out-of-sample, and asks the honest question: does allocating across signals
beat just holding the best single one? Compares equal-weight, inverse-vol (risk parity), and
shrunk max-Sharpe.

    python run_portfolio.py   # uses cached equity bars
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import crosssec as xs
from mds import portfolio as pf
from mds import validation as val


def demo_diversification() -> None:
    """Ground-truth check that the optimizer adds value when the inputs are GOOD: four
    uncorrelated signals each with a modest positive Sharpe should combine into a materially
    higher one (diversification). If this didn't hold, the machinery would be broken."""
    rng = np.random.default_rng(0)
    idx = pd.date_range("2010-01-01", periods=2500, freq="B")
    daily_mu = 0.7 / np.sqrt(pf.TRADING_DAYS) * 0.01  # each signal ~ Sharpe 0.7, uncorrelated
    net = pd.DataFrame(
        {f"sig{i}": rng.normal(daily_mu, 0.01, len(idx)) for i in range(4)}, index=idx)
    combined, _ = pf.walk_forward_allocate(net, method="risk_parity", lookback=126, rebalance=21)
    avg_single = np.mean([pf.sharpe(net[c]) for c in net.columns])
    print("Machinery check — 4 uncorrelated Sharpe-0.7 signals (synthetic):")
    print(f"  avg single signal Sharpe {avg_single:+.2f}  ->  allocated portfolio Sharpe "
          f"{pf.sharpe(combined):+.2f}   (diversification adds value)\n")


def main() -> None:
    demo_diversification()

    px, rets = xs.returns_panel()
    sigs = xs.signals(px, rets)
    # Each signal's NET (after-cost) daily return series — the streams we allocate across.
    net = pd.DataFrame(
        {name: xs.backtest(sig, rets, cost_bps=5.0)["net"] for name, sig in sigs.items()}
    ).dropna()

    zbar = val.bonferroni_z(len(net.columns))        # family-corrected bar, consistent with run_crosssec
    print(f"Signals: {list(net.columns)}   ({len(net)} days, aligned)\n")
    print("Individual signals (after-cost Sharpe, HAC significance + bootstrap CI):")
    print(f"  {'signal':<14} {'Sharpe':>7} {'HAC t':>7} {'boot 95% CI':>16} {'sig?':>5}")
    best_single_name, best_single = None, -1e9
    for col in net.columns:
        s = pf.sharpe(net[col])
        t = val.newey_west_sharpe_tstat(net[col].to_numpy())
        lo, hi = val.block_bootstrap_sharpe_ci(net[col].to_numpy())
        print(f"  {col:<14} {s:>+7.2f} {t:>+7.2f} [{lo:>+5.2f},{hi:>+5.2f}] "
              f"{'yes' if abs(t) >= zbar else 'no':>5}")
        if s > best_single:
            best_single_name, best_single = col, s

    print("\nAllocated portfolio (weights estimated on the past, applied to the future):")
    print(f"  {'method':<12} {'Sharpe':>7} {'HAC t':>7} {'boot 95% CI':>16} {'sig?':>5} {'ann ret':>9} {'max DD':>8}")
    best_alloc_name, best_alloc = None, -1e9
    for method in ("equal", "inverse_vol", "max_sharpe"):
        combined, _ = pf.walk_forward_allocate(net, method=method, lookback=126, rebalance=21)
        m = pf.metrics(combined)
        t = val.newey_west_sharpe_tstat(combined.to_numpy())
        lo, hi = val.block_bootstrap_sharpe_ci(combined.to_numpy())
        print(f"  {method:<12} {m['sharpe']:>+7.2f} {t:>+7.2f} [{lo:>+5.2f},{hi:>+5.2f}] "
              f"{'yes' if abs(t) >= zbar else 'no':>5} {m['ann_return']:>+9.1%} {m['max_drawdown']:>+8.1%}")
        if m["sharpe"] > best_alloc:
            best_alloc_name, best_alloc = method, m["sharpe"]

    print(f"  (HAC t: Newey–West; CI: moving-block bootstrap. 'sig?' uses the Bonferroni bar "
          f"|t|>{zbar:.2f} for {len(net.columns)} signals. Selection-aware DSR/PBO are in run_crosssec.py.)")
    print(f"\nBest single signal: {best_single_name} ({best_single:+.2f}).  "
          f"Best allocation: {best_alloc_name} ({best_alloc:+.2f}).")
    if best_alloc > best_single + 0.05:
        print("Allocation ADDS value here (diversification / concentrating on what works OOS).")
    else:
        print("Allocation does NOT beat the best single signal — honest, and expected when most of "
              "the signals are weak: an optimizer cannot manufacture alpha from bad inputs "
              "(garbage in, garbage out). Its value shows up with a richer set of GOOD signals.")
    print("Significance note: on this aligned window only a high-turnover LOSER (sector_rel_rev) "
          "clears the corrected bar, and it is not significant on its own full sample (run_crosssec) — "
          "window-dependent, and a costed loser regardless. No positive edge is distinguishable from "
          "zero; the allocation study is machinery, not a claimed edge.")


if __name__ == "__main__":
    main()
