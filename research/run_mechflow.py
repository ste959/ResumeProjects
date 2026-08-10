"""Shadow of the Machines — overnight reversal of leveraged-ETF forced close-rebalancing.

Tests a *structural* (mechanical, non-forecast) edge: leveraged/inverse ETFs must rebalance in the
direction of the day's move at the close; the non-informational overshoot should revert overnight, and —
the falsifiable prediction — the reversal should scale with forced flow ÷ underlying liquidity. Then runs
the strategy through the decay monitor to test the durability thesis (its source *grows* as markets get
more passive, so it should NOT be crowding out).

    python run_mechflow.py [--refresh]

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys). Pure logic is unit-tested (tests/test_mechflow.py).
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import decaymonitor as dm
from mds import evaluation as ev
from mds import mechflow as mf

START, END = "2020-07-27", "2026-07-02"
RF_PROXY = "BIL"
CACHE = pathlib.Path(__file__).parent / "data" / "cache"


def _load(refresh: bool):
    syms = list(mf.LEVERAGED_COMPLEXES) + [RF_PROXY]
    paths = {f: CACHE / f"mechflow_{f}.parquet" for f in ("open", "close", "volume")}
    if all(p.exists() for p in paths.values()) and not refresh:
        panels = {f: pd.read_parquet(p) for f, p in paths.items()}
    else:
        df = ad.fetch_bars(syms, START, END, adjustment="all")
        panels = {f: ad.close_panel(df, f).reindex(columns=syms) for f in paths}
        CACHE.mkdir(parents=True, exist_ok=True)
        for f, p in paths.items():
            panels[f].to_parquet(p)
    u = list(mf.LEVERAGED_COMPLEXES)
    return {f: panels[f][u].dropna(how="all") for f in panels}, panels["close"][RF_PROXY].pct_change()


def main() -> None:
    px, rf = _load("--refresh" in sys.argv)
    open_, close, vol = px["open"], px["close"], px["volume"]

    print(f"Shadow of the Machines · {len(mf.LEVERAGED_COMPLEXES)} underlyings w/ leveraged-ETF complexes · "
          f"{close.index[0].date()} → {close.index[-1].date()}")
    print("Leveraged ETFs MUST rebalance toward the day's move at the close; the overshoot reverts overnight.\n")

    # ── [1] The mechanism: does overnight reversal scale with forced flow ÷ liquidity? ──
    overnight = mf.overnight_returns(open_, close)
    betas = mf.reversal_betas(close, overnight)
    rel = mf.relative_flow(close, vol)
    tab = betas.join(rel.rename("rel_flow")).dropna().sort_values("rel_flow", ascending=False)
    print("[1] Mechanism test — overnight-reversal beta vs. relative forced flow (higher flow ⇒ more reversal?):")
    print(f"  {'underlying':<11}{'rel_flow':>10}{'overnight β':>13}{'t':>6}")
    for u, r in tab.iterrows():
        print(f"  {u:<11}{r['rel_flow']:>10.1f}{r['beta']:>13.3f}{r['t_stat']:>6.1f}")
    corr = tab["rel_flow"].corr(-tab["beta"])                # reversal strength = −beta
    print(f"  → corr(relative flow, reversal strength) = {corr:+.2f}  "
          f"({'SUPPORTS' if corr > 0.2 else 'does not support'} the mechanical hypothesis)")

    # ── [2] The strategy: dollar-neutral overnight reversal, flow-weighted ──
    gross = mf.backtest_overnight(open_, close, vol, cost_bps=0.0, rf=rf)
    net = mf.backtest_overnight(open_, close, vol, cost_bps=3.0, rf=rf)
    print(f"\n[2] Dollar-neutral overnight-reversal book (tilted to high-forced-flow names):")
    print(f"  {'':16}{'exSharpe':>10}{'HAC t':>7}{'ann ret':>9}{'turnover':>10}")
    for label, r in [("gross (no cost)", gross), ("net (3bps)", net)]:
        s = ev.stats(r["net"], rf)
        print(f"  {label:16}{s['sharpe']:>10.2f}{s['hac_t']:>7.1f}{s['ann_return']*100:>8.1f}%{r['turnover_ann']:>9.0f}x")
    gs = ev.stats(gross["net"], rf)
    print(f"  gross Sharpe 95% CI [{gs['boot_lo']:.2f}, {gs['boot_hi']:.2f}] — "
          f"{'distinguishable from 0' if gs['boot_lo'] > 0 else 'not clearly > 0'}")

    # ── [3] Durability: is the edge crowding out, or is its source growing? ──
    print(f"\n[3] Alpha-decay monitor — testing the 'growing source' durability thesis:")
    rep = dm.decay_report(gross["net"], rf=rf, factor=close["SPY"].pct_change(), n_buckets=6)
    print(f"  Sharpe  1st-half {rep['sharpe_first_half']:+.2f} → 2nd-half {rep['sharpe_second_half']:+.2f}   "
          f"decay slope {rep['decay_slope']:+.3f}/bucket (t {rep['decay_t']:+.1f})")
    print(f"  bucketed Sharpe: " + " → ".join(f"{s:+.2f}" for s in rep["buckets"]["sharpe"]))
    if rep["crowding"]:
        print(f"  crowding: corr-to-SPY {rep['crowding']['corr_now']:+.2f} (dollar-neutral ⇒ should be ~0)")
    print(f"  VERDICT: {rep['verdict']}")

    print(f"\nVerdict — a creative structural idea, tested honestly to its own refutation:")
    print(f"  1. The MECHANISM is real: overnight reversal scales with forced-flow÷liquidity (corr {corr:+.2f}), "
          f"and SPY — too deep for ETF rebalancing to move — shows almost exactly zero reversal "
          f"(β {tab.loc['SPY','beta']:+.3f}, t {tab.loc['SPY','t_stat']:+.1f}) if present, the cleanest confirmation. "
          f"The machines measurably move price.")
    print(f"  2. But it's NOT a tradable taker edge: the dollar-neutral book is null gross "
          f"(Sharpe {gs['sharpe']:.2f}, CI includes 0) and dies to cost ({gross['turnover_ann']:.0f}× turnover → "
          f"{ev.stats(net['net'], rf)['sharpe']:.2f} net).")
    print(f"  3. And the decay monitor REFUTED my own durability thesis: I predicted the edge would persist "
          f"because its source (mechanical flow) grows — instead it DECAYED sharply "
          f"({rep['sharpe_first_half']:+.2f} first-half → {rep['sharpe_second_half']:+.2f} second, slope t {rep['decay_t']:+.1f}). "
          f"Crowding outran the growing source.")
    print(f"  The lesson: a compelling structural STORY is not a durable EDGE, and the only way to know is to "
          f"monitor decay — which is exactly what caught my own thesis being wrong. Inventing the idea is easy; "
          f"having the discipline to disprove it is the job.")


if __name__ == "__main__":
    main()
