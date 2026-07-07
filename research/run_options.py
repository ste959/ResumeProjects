"""Options-implied cross-sectional signal study on Alpaca's LIVE option surface.

Fetches today's option chains for the universe, reduces each to its implied-vol signals (ATM IV,
25-delta skew, put/call volume), and ranks the cross-section. Then pairs ATM IV with a realized-vol
estimate from the cached daily bars to report the variance-risk-premium proxy (IV − RV) per name.

    python run_options.py               # live cross-section + IV−RV ranking (hits the API)
    python run_options.py --hist        # + a small historical-bars data-path demo (2-3 names)

HONEST SCOPING — this is a POINT-IN-TIME signal, NOT a backtest. Alpaca option snapshots are the
live surface; there is no free historical IV panel. A cross-sectional backtest of these signals
would need one of:
  (a) ACCUMULATING daily snapshots — schedule cross_section() daily (like the L2 tape capture),
      building an IV panel forward from today; or
  (b) a per-contract HISTORICAL fetch — /v1beta1/options/bars (data starts ~2024-02) giving option
      PRICE history, then a Black–Scholes inversion per bar to IV, plus identifying which contract
      was ATM/25Δ on each past date. Heavy AND gated: this account has no signed OPRA agreement, so
      that endpoint returns 403 (--hist demonstrates the gating directly).
This script delivers the live signal end-to-end and OUTLINES (b); it does NOT fabricate a backtest.
"""

from __future__ import annotations

import datetime as dt
import sys

import numpy as np
import pandas as pd

from mds import crosssec as xs
from mds import options as opt

TRADING_DAYS = 252


def realized_vol(window: int = 21) -> pd.Series:
    """Annualized trailing realized vol per name from the cached daily log returns — the RV in
    IV − RV. Uses the last `window` returns as of the most recent cached bar."""
    _, rets = xs.returns_panel()
    rv = rets.tail(window).std(ddof=0) * np.sqrt(TRADING_DAYS)
    return rv


def _show(df: pd.DataFrame, col: str, label: str, k: int = 8, fmt: str = "{:+.3f}") -> None:
    d = df[np.isfinite(df[col])].sort_values(col, ascending=False)
    print(f"\n{label} — highest:")
    for _, r in d.head(k).iterrows():
        print(f"  {r['symbol']:<6} {fmt.format(r[col]):>9}   (ATM IV {r['atm_iv']:.1%}, "
              f"exp {r['expiry']}, {int(r['n_contracts'])} contracts)")
    print(f"{label} — lowest:")
    for _, r in d.tail(k).iloc[::-1].iterrows():
        print(f"  {r['symbol']:<6} {fmt.format(r[col]):>9}   (ATM IV {r['atm_iv']:.1%}, "
              f"exp {r['expiry']}, {int(r['n_contracts'])} contracts)")


def historical_demo(names=("AAPL", "NVDA", "TSLA")) -> None:
    """Probe the historical data path (option-price bars) and report what the account can actually
    reach — WITHOUT fabricating IV. On an OPRA-signed account this shows the available window/bar
    count (the raw material a real historical IV study would BS-invert); on this account it surfaces
    the 403 OPRA gating honestly."""
    print("\n" + "=" * 78)
    print("HISTORICAL DATA-PATH PROBE (option-price bars — NOT a backtest, NOT IV)")
    print("=" * 78)
    start, end = "2024-02-01", dt.date.today().isoformat()
    for sym in names:
        occ = opt.atm_contract(sym)
        if occ is None:
            print(f"  {sym:<6} no ATM contract resolved — skipped")
            continue
        bars, status = opt.option_bars(occ, start, end)
        if status != "ok":
            print(f"  {sym:<6} {occ}: no bars ({status})")
            continue
        print(f"  {sym:<6} {occ}: {len(bars)} daily price bars, "
              f"{bars['ts'].min().date()} → {bars['ts'].max().date()} "
              f"(last close ${bars['close'].iloc[-1]:.2f})")
    print("\n  /v1beta1/options/bars is OPRA-only; this key has no signed OPRA agreement, so it 403s.")
    print("  Even WITH it, a historical IV panel = per-bar Black–Scholes inversion (underlying +")
    print("  strike + dte + rate → IV) on the contract that was ATM/25Δ on each past date. That")
    print("  gating + contract-identification + inversion is the heavy part deferred above. The")
    print("  free-tier path to a backtest is therefore (a): schedule cross_section() to accrue")
    print("  daily snapshots into an IV panel going forward, exactly like the L2 tape capture.")


def main() -> None:
    asof = dt.date.today()
    print(f"Options-implied cross-section — LIVE surface as of {asof} (indicative feed)")
    print("Fetching option chains for the 123-name universe (nearest expiries, ≤45 DTE)...")

    df = opt.cross_section(opt.UNIVERSE, asof=asof)
    n_total = len(opt.UNIVERSE)
    n_hit = len(df)
    print(f"\n{n_hit}/{n_total} names returned a usable option chain "
          f"(chain present + a qualifying expiry with both wings).")
    if df.empty:
        print("No chains returned — check credentials / market hours. Nothing to rank.")
        return

    # IV − RV: implied ATM vol minus 21-day realized vol (the variance-risk-premium proxy).
    rv = realized_vol(21)
    df["rv_21d"] = df["symbol"].map(rv)
    df["iv_minus_rv"] = df["atm_iv"] - df["rv_21d"]

    print(f"\nCross-section summary (N={n_hit}):")
    print(f"  ATM IV      median {df['atm_iv'].median():.1%}   "
          f"range [{df['atm_iv'].min():.1%}, {df['atm_iv'].max():.1%}]")
    print(f"  25Δ skew    median {df['skew_25d'].median():+.3f}   "
          f"range [{df['skew_25d'].min():+.3f}, {df['skew_25d'].max():+.3f}]")
    print(f"  put/call V  median {df['pcr_volume'].median():.2f}")
    print(f"  IV − RV(21) median {df['iv_minus_rv'].median():+.1%}   "
          f"({(df['iv_minus_rv'] > 0).mean():.0%} of names have IV > RV — the vol premium)")

    _show(df, "skew_25d", "25-DELTA SKEW (downside fear: IV[25Δ put] − IV[25Δ call])")
    _show(df, "atm_iv", "ATM IMPLIED VOL", fmt="{:.1%}")
    _show(df, "iv_minus_rv", "IV − REALIZED VOL (variance-risk-premium proxy)", fmt="{:+.1%}")

    print("\n" + "-" * 78)
    print("SCOPING: the table above is TODAY's cross-section (point-in-time), not a backtest.")
    print("Snapshots are live; a cross-sectional backtest needs a historical IV panel via either")
    print("  (a) a scheduled daily cross_section() capture (build the panel forward, like the L2")
    print("      tape), or (b) /v1beta1/options/bars per contract + a Black–Scholes inversion.")
    print("Neither is fabricated here. Run with --hist to see the (b) data path is reachable.")

    if len(sys.argv) > 1 and sys.argv[1] == "--hist":
        historical_demo()


if __name__ == "__main__":
    main()
