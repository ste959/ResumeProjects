"""Risk & TCA — the risk system and the paper-vs-reality ledger for a live strategy.

Takes the trend book through the platform's risk stack:
  • a **risk report** — realized vol, historical & Cornish–Fisher VaR, expected shortfall, and the risk
    contribution by sleeve (where the risk actually lives);
  • **stress tests** — the current book replayed through historical shock windows;
  • **limit checks** — the book against a mandate;
  • **implementation shortfall** (TCA) — the paper-vs-realistic gap split into execution vs. opportunity cost.

    python run_risk.py [--refresh]

Needs ALPACA_KEY_ID / ALPACA_SECRET_KEY (free keys). All analytics are pure and unit-tested
(tests/test_riskmgmt.py, tests/test_tca.py); this driver supplies real data.
"""

from __future__ import annotations

import pathlib
import sys

import pandas as pd

from mds import alpaca_data as ad
from mds import engine as eng
from mds import execution as ex
from mds import riskmgmt as rm
from mds import strategies_lib as sl
from mds import tca
from mds import trend as tr

START, END = "2020-07-27", "2026-07-02"
RF_PROXY = "BIL"
IEX_VOLUME_SHARE = 0.04
CACHE = pathlib.Path(__file__).parent / "data" / "cache"

# Historical stress windows inside the sample (the pre-2020-07 COVID crash is before our data).
SCENARIOS = [
    ("2022 rate shock (stx+bnds)", "2022-01-01", "2022-10-31"),
    ("Mar-2023 banking (SVB/CS)", "2023-03-01", "2023-03-31"),
    ("Aug-2024 vol spike", "2024-07-25", "2024-08-09"),
    ("Apr-2025 tariff selloff", "2025-04-01", "2025-04-30"),
]


def _load(refresh: bool):
    syms = list(tr.UNIVERSE) + [RF_PROXY]
    paths = {f: CACHE / f"exec_{f}.parquet" for f in ("close", "high", "low", "volume")}
    if all(p.exists() for p in paths.values()) and not refresh:
        panels = {f: pd.read_parquet(p) for f, p in paths.items()}
    else:
        df = ad.fetch_bars(syms, START, END, adjustment="all")
        panels = {f: ad.close_panel(df, f).reindex(columns=syms).dropna() for f in paths}
        CACHE.mkdir(parents=True, exist_ok=True)
        for f, p in paths.items():
            panels[f].to_parquet(p)
    rf = panels["close"][RF_PROXY].pct_change()
    u = list(tr.UNIVERSE)
    return {f: panels[f][u] for f in panels}, rf


def main() -> None:
    px, rf = _load("--refresh" in sys.argv)
    close = px["close"]
    liq = ex.estimate_liquidity(close, px["volume"] / IEX_VOLUME_SHARE, px["high"], px["low"])
    syms = list(tr.UNIVERSE)
    strat = sl.TimeSeriesMomentum(syms)

    res = eng.run(strat, close, eng.BacktestConfig(execution=ex.RealisticExecution(), aum=5e8, rf=rf), liq)
    cov = close.pct_change().dropna().cov().to_numpy()   # DAILY covariance (risk_report annualizes it)
    latest_w = res.weights.iloc[-1]                       # the current book

    print(f"Risk & TCA · {strat.name} · realistic execution · $500M · {close.index[0].date()} → {close.index[-1].date()}\n")

    # ── risk report ──
    rep = rm.risk_report(res.net, weights=latest_w, cov=cov, sleeves=tr.SLEEVES)
    print("[1] Risk report (daily VaR/ES are positive loss fractions):")
    print(f"    realized vol {rep['ann_vol']*100:.1f}%/yr   ex-ante vol {rep['exante_ann_vol']*100:.1f}%/yr")
    print(f"    VaR95 hist {rep['var_95_hist']*100:.2f}%   VaR95 Cornish-Fisher {rep['var_95_cornish_fisher']*100:.2f}%  "
          f"(fat-tail adj)   VaR99 {rep['var_99_hist']*100:.2f}%   ES95 {rep['cvar_95']*100:.2f}%")
    print("    risk contribution by sleeve: " +
          "  ".join(f"{k} {v*100:+.0f}%" for k, v in rep["risk_contribution"].items()))

    # ── stress ──
    print("\n[2] Stress test — the CURRENT book replayed through historical shocks:")
    for s in rm.stress_test(latest_w, close, SCENARIOS):
        print(f"    {s['scenario']:<28} {s['book_return']*100:>+6.1f}%   worst day {s['worst_day']*100:>+5.1f}%  "
              f"({s['n_days']}d)")

    # ── limits ──
    print("\n[3] Limit checks (book vs. mandate):")
    for c in rm.check_limits(res.weights, res.net, rm.RiskLimits(), sleeves=tr.SLEEVES):
        flag = "BREACH" if c["breached"] else "ok"
        print(f"    {c['limit']:<18} {c['value']:>7.3f}  vs cap {c['cap']:>6.3f}   [{flag}]")

    # ── TCA ──
    print("\n[4] Implementation shortfall (paper → reality, annualized):")
    for aum in (1e8, 5e8, 2e9):
        s = tca.implementation_shortfall(strat, close, liq, eng.BacktestConfig(rf=rf), aum=aum)
        label = f"${aum/1e6:.0f}M" if aum < 1e9 else f"${aum/1e9:.0f}B"
        print(f"    {label:>6}: ideal {s['ideal_ann_return']*100:>+5.1f}% → real {s['realistic_ann_return']*100:>+5.1f}%   "
              f"exec cost {s['execution_cost_annual']*100:>4.2f}%   opportunity {s['opportunity_cost_annual']*100:>4.2f}%   "
              f"total IS {s['total_shortfall_annual']*100:>4.2f}%")

    print(f"\nVerdict: the risk system says where the risk lives (sleeve contributions), what a crisis does to "
          f"today's book (stress), and whether it's inside mandate (limits). The TCA ledger shows the paper "
          f"strategy and the real one are different animals — and splits the difference into what you paid to "
          f"trade (execution) vs. what you lost by being unable to trade at size (opportunity). A strategy "
          f"isn't real until it survives all four.")


if __name__ == "__main__":
    main()
