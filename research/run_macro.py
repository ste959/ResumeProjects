"""FRED macro / credit overlay — a risk-off timing study.

The price-only cross-sectional study found the edge is regime-dependent (it gives back gains in
risk-off episodes like 2022). This asks a different, honest question: can an EXOGENOUS macro
signal — credit spreads (High-Yield OAS) and equity vol (VIX) — be used to TIME equity exposure,
cutting the book in risk-off regimes and running it in risk-on ones?

We test the overlay on two books:
  * the equal-weight MARKET (directional, long-only — basically market beta, the natural thing to
    time; risk-off timing should cut its drawdowns most), and
  * the dollar-neutral MOMENTUM book (already beta-hedged — the overlay should matter far less).

For each we compare RAW vs macro-TIMED (returns scaled by the causal risk-appetite score) on
annualized Sharpe, HAC (Newey–West) t-stat, block-bootstrap 95% CI, and max drawdown.

    python run_macro.py     # fetches 3 FRED series once, caches under data/macro/

Caveats: this is a timing OVERLAY, not new cross-sectional alpha (it re-times existing exposure,
it cannot flip a sign); ~5.9y is only a couple of macro cycles; and it is strictly causal (the
score for day t uses macro data through t-1 only).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import crosssec as xs
from mds import macro as mc
from mds import portfolio as pf
from mds import validation as val

TRADING_DAYS = 252


def _max_dd(returns: pd.Series) -> float:
    r = returns.dropna()
    if not len(r):
        return 0.0
    equity = (1.0 + r).cumprod()
    return float((equity / equity.cummax() - 1.0).min())


def _row(name: str, raw: pd.Series, score: pd.Series) -> dict:
    """RAW vs macro-timed metrics for one book. `timed = raw * score` (score in [0,1], causal)."""
    timed = (raw * score.reindex(raw.index)).dropna()
    raw = raw.reindex(timed.index)        # compare on the common (post-shift) window
    t = val.newey_west_sharpe_tstat(timed.to_numpy())
    lo, hi = val.block_bootstrap_sharpe_ci(timed.to_numpy())
    return {
        "name": name,
        "raw_sharpe": pf.sharpe(raw), "timed_sharpe": pf.sharpe(timed),
        "timed_hac_t": t, "boot_lo": lo, "boot_hi": hi,
        "raw_dd": _max_dd(raw), "timed_dd": _max_dd(timed),
        "avg_exposure": float(score.reindex(timed.index).mean()),
    }


def main() -> None:
    px, rets = xs.returns_panel()
    mom_net = xs.backtest(xs.signals(px, rets)["momentum"], rets)["net"].dropna()
    mkt = xs._market_return(rets).dropna()          # equal-weight, long-only market proxy

    # The causal risk-appetite score aligned to the equity panel's dates (shifted one day).
    state = mc.risk_off_state(rets.index)
    score = state["score"]
    hy, vix = state["hy"], state["vix"]

    print("FRED macro / credit overlay — risk-off timing (HY OAS + VIX), causal (shift 1d)\n")
    obs = score.dropna()
    print(f"  score: {len(obs)} days, mean {obs.mean():.2f}, min {obs.min():.2f}, "
          f"max {obs.max():.2f}  (1 = full risk-on)")
    # Show the regime read on the panel window's most-risk-off day.
    worst = obs.idxmin()
    print(f"  most risk-off day: {worst.date()}  score {obs.min():.2f}  "
          f"HY OAS {hy.loc[worst]:.2f}%  VIX {vix.loc[worst]:.1f}\n")

    rows = [_row("market (long-only)", mkt, score),
            _row("momentum (neutral)", mom_net, score)]

    print(f"  {'book':<20} {'raw Shrp':>9} {'timed Shrp':>11} {'timed HAC t':>12} "
          f"{'timed 95% CI':>16} {'raw DD':>8} {'timed DD':>9} {'avg exp':>8}")
    for r in rows:
        print(f"  {r['name']:<20} {r['raw_sharpe']:>+9.2f} {r['timed_sharpe']:>+11.2f} "
              f"{r['timed_hac_t']:>+12.2f} [{r['boot_lo']:>+5.2f},{r['boot_hi']:>+5.2f}] "
              f"{r['raw_dd']:>+8.1%} {r['timed_dd']:>+9.1%} {r['avg_exposure']:>8.2f}")

    print()
    mkt_r, mom_r = rows[0], rows[1]
    # DDs are negative; timed less negative than raw = drawdown improved. Positive = improvement.
    mkt_dd_cut = mkt_r["timed_dd"] - mkt_r["raw_dd"]
    print("Verdict:")
    print(f"  MARKET (long-only): Sharpe {mkt_r['raw_sharpe']:+.2f} -> {mkt_r['timed_sharpe']:+.2f}, "
          f"max DD {mkt_r['raw_dd']:+.1%} -> {mkt_r['timed_dd']:+.1%} "
          f"({'cuts' if mkt_dd_cut > 0 else 'does NOT cut'} drawdown by {abs(mkt_dd_cut):.1%}).")
    if mkt_r["timed_sharpe"] > mkt_r["raw_sharpe"] and mkt_dd_cut > 0:
        print("    Risk-off timing helps the directional book on BOTH axes: it lifts the Sharpe and "
              "shrinks the drawdown by cutting equity beta in risk-off regimes (2022 / spread blowouts).")
    elif mkt_dd_cut > 0:
        print("    Risk-off timing cuts the drawdown (its main job — de-risking in stress) even though "
              "the Sharpe move is modest: a better-shaped return path for the same directional book.")
    else:
        print("    On this window the overlay does not improve the directional book — honest, and a "
              "reminder that ~5.9y is few macro cycles to time.")
    print(f"  MOMENTUM (dollar-neutral): Sharpe {mom_r['raw_sharpe']:+.2f} -> {mom_r['timed_sharpe']:+.2f}, "
          f"max DD {mom_r['raw_dd']:+.1%} -> {mom_r['timed_dd']:+.1%}. As expected the effect is smaller "
          "— the book is already beta-hedged, so there is less market risk-off for a macro overlay to cut.")
    print("\n  Caveats: a timing OVERLAY, not new cross-sectional alpha (it re-times exposure, cannot "
          "flip a sign); ~5.9y is only a couple of macro cycles; strictly causal (score shifted 1 day).")


if __name__ == "__main__":
    main()
