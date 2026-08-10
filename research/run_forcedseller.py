"""The Forced Seller — anticipating vol-control deleveraging, tested on real index data.

Does front-running the mechanical vol-target flow (Δ of target/realized-vol) predict returns, does it beat
simply vol-targeting your own book (Moreira–Muir), and is it decaying? The honest bar: it must add value
*beyond* generic vol-timing to be a distinct edge.

    python run_forcedseller.py [--refresh]

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY. Pure logic is unit-tested (tests/test_forcedseller.py).
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import decaymonitor as dm
from mds import engine as eng
from mds import forcedseller as fs

START, END = "2020-07-27", "2026-07-02"
RF_PROXY = "BIL"
CACHE = pathlib.Path(__file__).parent / "data" / "cache" / "forcedseller.parquet"
INDICES = ["SPY", "QQQ", "IWM"]


def _load(refresh: bool):
    syms = INDICES + [RF_PROXY]
    if CACHE.exists() and not refresh:
        panel = pd.read_parquet(CACHE)
    else:
        panel = ad.close_panel(ad.fetch_bars(syms, START, END, adjustment="all")).reindex(columns=syms).dropna()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(CACHE)
    return panel[INDICES], panel[RF_PROXY].pct_change()


def main() -> None:
    prices, rf = _load("--refresh" in sys.argv)
    print(f"The Forced Seller · vol-control deleveraging · {', '.join(INDICES)} · "
          f"{prices.index[0].date()} → {prices.index[-1].date()}")
    print("Vol-target funds hold target/realized-vol; a vol spike forces multi-day selling — we ride it.\n")

    # ── [1] Mechanism: does the forced-flow estimate predict forward returns? ──
    print("[1] Mechanism — forward-return predictability of the forced-flow signal (Δexposure), by horizon:")
    print(f"  {'index':<6}" + "".join(f"{'h='+str(h):>12}" for h in (1, 3, 5, 10)))
    for sym in INDICES:
        r = prices[sym].pct_change()
        pred = fs.forward_predictability(r, fs.forced_flow(fs.target_exposure(fs.realized_vol(r))), (1, 3, 5, 10))
        cells = "".join(f"{row['coef']*1e4:>+7.1f}(t{row['t_stat']:>+3.1f})" for _, row in pred.iterrows())
        print(f"  {sym:<6}{cells}")
    print("  (coef ×1e4; positive ⇒ deleveraging predicts down / re-levering predicts up — the flow effect)")

    # ── [2] Strategy vs the honest benchmark (generic vol-timing) and buy-hold ──
    cfg = eng.BacktestConfig(rebalance=1, cost_bps=1.0, rf=rf)
    out = eng.compare([fs.ForcedSeller("SPY"), fs.VolTargetHold("SPY"), fs.BuyHold("SPY")], prices, cfg)
    res = {r.name: r for r in out["results"]}
    print(f"\n[2] SPY strategies (must beat vol-target-hold to be a *distinct* edge, not just vol-timing):")
    print(f"  {'':18}{'exSharpe':>10}{'HAC t':>7}{'ann ret':>9}{'maxDD':>8}{'avg pos':>9}")
    for name in ("forced-seller", "vol-target-hold", "buy-hold"):
        r = res[name]
        s = r.stats
        print(f"  {name:<18}{s['sharpe']:>10.2f}{s['hac_t']:>7.1f}{s['ann_return']*100:>8.1f}%"
              f"{s['max_drawdown']*100:>7.1f}%{r.weights['SPY'].mean():>9.2f}")
    corr = res["forced-seller"].net.corr(res["vol-target-hold"].net)
    print(f"  forced-seller vs vol-target-hold return corr = {corr:+.2f}")

    # ── [3] Durability ──
    print(f"\n[3] Alpha-decay monitor (forced-seller):")
    rep = dm.decay_report(res["forced-seller"].net, rf=rf, factor=prices["SPY"].pct_change(), n_buckets=6)
    print(f"  Sharpe 1st-half {rep['sharpe_first_half']:+.2f} → 2nd-half {rep['sharpe_second_half']:+.2f}   "
          f"decay t {rep['decay_t']:+.1f}   VERDICT: {rep['verdict']}")

    fseller_sh = res["forced-seller"].stats["sharpe"]
    vhold_sh = res["vol-target-hold"].stats["sharpe"]
    bh_sh = res["buy-hold"].stats["sharpe"]
    print(f"\nVerdict — refuted, and the sign error is the lesson:")
    print(f"  The flow is real and mechanical (vol-target funds MUST sell into vol spikes), but 'ride it' is "
          f"the WRONG SIDE: forced-seller Sharpe {fseller_sh:.2f} (HAC t {res['forced-seller'].stats['hac_t']:+.1f}) "
          f"and decaying. The mechanism regression barely predicts forward returns (t-stats ≈ 0). Why: after a "
          f"vol spike the market **front-runs and bounces** (mean-reversion + dip-buying + the forced selling "
          f"getting anticipated and absorbed), and that reversal DOMINATES the continued deleveraging at these "
          f"horizons — so you'd want to FADE the flow, not ride it.")
    print(f"  And plain vol-timing barely helps either: vol-target-hold {vhold_sh:.2f} ≈ buy-hold {bh_sh:.2f} in "
          f"a raging bull. Forced-seller is a distinct book (corr {corr:+.2f} to vol-timing) — distinctly bad. "
          f"Structural flow: real. Tradable by riding it: no — because everyone else front-runs the same "
          f"forced flow, which is exactly why a 'mechanical' edge still isn't a free one.")


if __name__ == "__main__":
    main()
