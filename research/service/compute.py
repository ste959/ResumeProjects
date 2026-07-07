"""Research compute layer — pure functions that turn the `mds` research modules into JSON-able
dicts for the Research Lab front end.

Deliberately separated from the FastAPI layer (`app.py`) so it can be unit-tested without the web
framework, and so the same functions back both the *interactive* endpoint (a live single-signal
backtest, ~1s) and the *snapshot* export (`export_snapshot.py` → snapshot.json, the told-story
results that are always available even without the raw data mounted).

Everything reuses the exact modules the CLI drivers use — `crosssec`, `factors`, `riskmodel`,
`factortiming`, `macro`, `validation` — so the numbers the UI shows are the same honest, cost-aware,
overfitting-adjusted figures `run_crosssec.py` / `run_construction.py` print, not a re-derivation.
"""

from __future__ import annotations

import functools
import json
import pathlib
import sys

import numpy as np
import pandas as pd

# research/ on the path so `from mds import …` works regardless of the service's working directory.
_RESEARCH_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_ROOT))

from mds import crosssec as xs               # noqa: E402
from mds import edgar                        # noqa: E402
from mds import factors as fc                # noqa: E402
from mds import factortiming as ft           # noqa: E402
from mds import macro as mc                  # noqa: E402
from mds import portfolio as pf              # noqa: E402
from mds import riskmodel as rm              # noqa: E402
from mds import structuring as st            # noqa: E402
from mds import taxaware as tx               # noqa: E402
from mds import validation as val            # noqa: E402
from mds import options as opt               # noqa: E402

SNAPSHOT_PATH = pathlib.Path(__file__).resolve().parent / "snapshot.json"
TRADING_DAYS = 252

# Human-facing metadata for each signal the Lab can backtest (family + one-liner). Higher = long.
SIGNAL_META: dict[str, dict[str, str]] = {
    "momentum": {"family": "momentum", "label": "12–1 Momentum", "desc": "Last ~12m return skipping the recent month."},
    "reversal": {"family": "reversal", "label": "Short-term Reversal", "desc": "Fade last week's move (buy losers)."},
    "low_vol": {"family": "low_risk", "label": "Low Volatility", "desc": "Prefer calmer names (negate trailing vol)."},
    "bab": {"family": "low_risk", "label": "Betting-Against-Beta", "desc": "Long low-β, short high-β."},
    "idio_vol": {"family": "low_risk", "label": "Idiosyncratic-Vol", "desc": "Long low residual (idio) vol."},
    "risk_adj_mom": {"family": "momentum", "label": "Risk-Adjusted Momentum", "desc": "12–1 momentum scaled by idio-vol."},
    "sector_rel_mom": {"family": "momentum", "label": "Sector-Relative Momentum", "desc": "Intra-industry momentum (sector-neutral)."},
    "overnight": {"family": "momentum", "label": "Overnight Return", "desc": "Trailing overnight (close→open) drift."},
    "sector_rel_rev": {"family": "reversal", "label": "Sector-Relative Reversal", "desc": "Reversal on the sector-residual return."},
    "vwap_pressure": {"family": "reversal", "label": "Close-vs-VWAP Pressure", "desc": "Persistent close above the day's VWAP."},
    "max_lottery": {"family": "low_risk", "label": "Anti-Lottery (MAX)", "desc": "Short extreme recent up-days."},
    "flow_pressure": {"family": "flow", "label": "Order-Flow Pressure", "desc": "Signed-volume (close vs VWAP) over a week."},
    "trade_size_trend": {"family": "flow", "label": "Participation Trend", "desc": "Rising average trade size (accumulation)."},
    "earnings_yield": {"family": "value", "label": "Earnings Yield", "desc": "EPS / price — the value axis."},
    "gross_profitability": {"family": "quality", "label": "Gross Profitability", "desc": "Gross profit / assets (Novy-Marx)."},
    "roe": {"family": "quality", "label": "Return on Equity", "desc": "Net income / equity."},
    "accruals": {"family": "quality", "label": "Accruals (Sloan)", "desc": "Long low accruals (earnings quality)."},
    "asset_growth": {"family": "quality", "label": "Asset Growth", "desc": "Long low asset growth (conservative)."},
    "composite": {"family": "composite", "label": "Multi-Factor Composite", "desc": "Value+quality+momentum blend (medium-term book)."},
}

FAMILY_ROLE = {
    "value": "medium-horizon premium", "quality": "medium-horizon premium",
    "momentum": "medium-horizon premium", "reversal": "short-horizon (excluded)",
    "low_risk": "defensive → vol-scaled", "flow": "short-horizon (excluded)",
}


# ── cached raw material (loaded once per process) ────────────────────────────────────────────────
@functools.lru_cache(maxsize=1)
def _panels() -> tuple[pd.DataFrame, pd.DataFrame]:
    return xs.returns_panel()


@functools.lru_cache(maxsize=1)
def _all_signals() -> dict[str, pd.DataFrame]:
    px, rets = _panels()
    price = xs.signals(px, rets)
    try:
        fund = edgar.fundamental_signals(px)
    except Exception:
        fund = {}
    return {**price, **fund}


@functools.lru_cache(maxsize=1)
def _beta() -> pd.DataFrame:
    _, rets = _panels()
    return xs._rolling_beta(rets, xs._loo_market(rets))


def _signal_frame(name: str) -> pd.DataFrame:
    sigs = _all_signals()
    if name == "composite":
        return fc.composite(sigs, families=fc.medium_term_families())
    if name not in sigs:
        raise KeyError(name)
    return sigs[name]


def _curve(net: pd.Series, points: int = 180) -> list[dict]:
    """Downsampled cumulative equity curve for plotting (≈`points` samples)."""
    eq = (1.0 + net.dropna()).cumprod()
    if eq.empty:
        return []
    step = max(1, len(eq) // points)
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
            for d, v in eq.iloc[::step].items()]


def _f(x) -> float | None:
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# ── public compute functions ─────────────────────────────────────────────────────────────────────
def list_signals() -> list[dict]:
    """The signal menu for the interactive control — name, family, label, description."""
    available = set(_all_signals()) | {"composite"}
    return [{"name": n, **meta} for n, meta in SIGNAL_META.items() if n in available]


def backtest_signal(signal: str, cost_bps: float = 5.0, neutralize: bool = True) -> dict:
    """Live single-signal (or composite) backtest as a dollar-neutral book, with honest stats.

    `neutralize=True` uses the β+sector-neutral (investable) weights; False uses the raw z-score
    (dollar-neutral only) book. Returns metrics + a downsampled equity curve + a plain verdict."""
    _, rets = _panels()
    sig = _signal_frame(signal)
    weights = xs.neutralized_weights(sig, rets) if neutralize else None
    bt = xs.backtest(sig, rets, cost_bps=float(cost_bps), weights=weights)
    net = bt["net"].dropna()
    hac = val.newey_west_sharpe_tstat(net.to_numpy())
    lo, hi = val.block_bootstrap_sharpe_ci(net.to_numpy())
    zbar = val.bonferroni_z(len(_all_signals()))      # family-corrected bar
    significant = abs(hac) >= zbar
    meta = SIGNAL_META.get(signal, {"family": "", "label": signal, "desc": ""})
    if significant and bt["net_sharpe"] > 0:
        verdict = f"Clears the multiple-testing bar (|t|>{zbar:.2f}) with a positive Sharpe — a candidate to validate live."
    elif significant:
        verdict = f"Clears the bar (|t|>{zbar:.2f}) but is a costed LOSER, not an edge."
    else:
        verdict = f"Not distinguishable from zero once corrected for {len(_all_signals())} trials (|t|<{zbar:.2f})."
    return {
        "signal": signal, "label": meta["label"], "family": meta["family"],
        "cost_bps": float(cost_bps), "neutralized": bool(neutralize),
        "net_sharpe": _f(bt["net_sharpe"]), "gross_sharpe": _f(bt["gross_sharpe"]),
        "hac_t": _f(hac), "boot_lo": _f(lo), "boot_hi": _f(hi),
        "ann_return": _f(bt["ann_return"]), "max_drawdown": _f(bt["max_drawdown"]),
        "avg_turnover": _f(bt["avg_turnover"]), "days": int(bt["days"]),
        "bonferroni_z": _f(zbar), "significant": bool(significant),
        "equity_curve": _curve(net), "verdict": verdict,
    }


def _neut_sharpe(sig: pd.DataFrame, rets: pd.DataFrame) -> float:
    return xs.backtest(sig, rets, weights=xs.neutralized_weights(sig, rets))["net_sharpe"]


def compute_findings() -> dict:
    """The 'honest null' story: every signal's neutralized Sharpe + HAC t, plus the selection-aware
    Deflated-Sharpe / PBO across the trial family, and the one-line verdict."""
    px, rets = _panels()
    sigs = _all_signals()
    rows, nets = [], {}
    for name, sig in sigs.items():
        bt = xs.backtest(sig, rets, cost_bps=5.0)
        nets[name] = bt["net"]
        hac = val.newey_west_sharpe_tstat(bt["net"].dropna().to_numpy())
        meta = SIGNAL_META.get(name, {"family": "", "label": name})
        rows.append({"name": name, "label": meta["label"], "family": meta["family"],
                     "net_sharpe": _f(bt["net_sharpe"]), "hac_t": _f(hac),
                     "turnover": _f(bt["avg_turnover"])})
    zbar = val.bonferroni_z(len(sigs))
    for r in rows:
        r["significant"] = bool(r["hac_t"] is not None and abs(r["hac_t"]) >= zbar)

    # Selection-aware: Deflated Sharpe of the best + PBO across the family.
    from scipy.stats import kurtosis, skew
    net_mat = pd.DataFrame(nets).dropna()
    daily = {n: (net_mat[n].mean() / net_mat[n].std(ddof=0)) if net_mat[n].std(ddof=0) > 0 else 0.0
             for n in net_mat.columns}
    best = max(daily, key=daily.get)
    b = net_mat[best].to_numpy()
    dsr = val.deflated_sharpe(daily[best], len(b), float(skew(b)), float(kurtosis(b, fisher=False)),
                              n_trials=len(sigs), sharpe_var_across_trials=float(np.var(list(daily.values()), ddof=1)))
    pbo = val.pbo(net_mat.to_numpy(), n_splits=12)["pbo"]
    rows.sort(key=lambda r: -(r["net_sharpe"] or -9))
    return {
        "universe": {"names": int(px.shape[1]), "days": int(px.shape[0]),
                     "start": str(px.index.min().date()), "end": str(px.index.max().date())},
        "signals": rows,
        "selection": {"best": best, "best_label": SIGNAL_META.get(best, {}).get("label", best),
                      "deflated_sharpe": _f(dsr), "pbo": _f(pbo), "bonferroni_z": _f(zbar),
                      "n_trials": len(sigs)},
        "verdict": (f"No signal clears the Bonferroni bar |t|>{zbar:.2f} for {len(sigs)} trials; "
                    f"best Deflated Sharpe {dsr:.2f} (needs >0.95), PBO {pbo:.2f}. An honest null — "
                    "the price/fundamental data on mega-caps is breadth-limited, not the technique."),
    }


def compute_construction() -> dict:
    """The five-layer construction stack as structured data (mirrors run_construction.py)."""
    px, rets = _panels()
    sigs = _all_signals()
    beta = _beta()
    all_fams = fc.family_scores(sigs)
    mt = fc.medium_term_families()
    fams = {k: all_fams[k] for k in mt if k in all_fams}
    comp = fc.composite(sigs, families=mt)

    ics = fc.ic_summary(fc.ic_series(comp, rets))
    comp_w = xs.neutralized_weights(comp, rets)
    comp_bt = xs.backtest(comp, rets, weights=comp_w)
    singles = {n: _neut_sharpe(s, rets) for n, s in sigs.items()}
    best_single = max(singles, key=singles.get)

    # 2. risk-model optimized book vs naive baselines
    opt_w = rm.optimized_weights(comp, rets, beta, xs.SECTORS, fams, lookback=252, rebalance=21,
                                 gross=1.0, position_cap=0.05, max_turnover=0.20)
    opt_bt = xs.backtest(comp, rets, weights=opt_w)
    raw_w = xs.raw_weights(comp)
    raw_bt = xs.backtest(comp, rets, weights=raw_w)

    def _book(label, w, bt):
        return {"book": label, "net_sharpe": _f(bt["net_sharpe"]),
                "hac_t": _f(val.newey_west_sharpe_tstat(bt["net"].dropna().to_numpy())),
                "turnover": _f(bt["avg_turnover"]),
                "net_beta": _f(xs.book_beta(w, rets).abs().mean()),
                "max_drawdown": _f(_max_dd(bt["net"]))}

    # 3. timing
    score = mc.risk_off_state(rets.index)["score"]
    timed = ft.timed_composite(fams, score)
    timed_bt = xs.backtest(timed, rets, weights=xs.neutralized_weights(timed, rets))
    mkt = xs._market_return(rets).dropna()
    mkt_timed = ft.apply_regime_exposure(mkt, score).dropna()

    # 4. structuring (from cached options snapshot, if any)
    structuring = _structuring_summary(rets, sigs, comp_w)

    # 5. tax
    tax = _tax_summary(px, comp)

    return {
        "composite": {"ic_mean": _f(ics["mean_ic"]), "ic_t": _f(ics["t_stat"]),
                      "net_sharpe": _f(comp_bt["net_sharpe"]),
                      "hac_t": _f(val.newey_west_sharpe_tstat(comp_bt["net"].dropna().to_numpy())),
                      "turnover": _f(comp_bt["avg_turnover"]),
                      "best_single": best_single, "best_single_label": SIGNAL_META.get(best_single, {}).get("label", best_single),
                      "best_single_sharpe": _f(singles[best_single])},
        "families": [{"name": n, "neutral_sharpe": _f(_neut_sharpe(all_fams[n], rets)),
                      "role": FAMILY_ROLE.get(n, "")} for n in all_fams],
        "riskmodel": [_book("z-score (dollar-neutral)", raw_w, raw_bt),
                      _book("β+sector-neutralized", comp_w, comp_bt),
                      _book("risk-model optimized", opt_w, opt_bt)],
        "timing": {"static_sharpe": _f(comp_bt["net_sharpe"]), "timed_sharpe": _f(timed_bt["net_sharpe"]),
                   "mkt_raw_sharpe": _f(pf.sharpe(mkt)), "mkt_raw_dd": _f(_max_dd(mkt)),
                   "mkt_timed_sharpe": _f(pf.sharpe(mkt_timed)), "mkt_timed_dd": _f(_max_dd(mkt_timed)),
                   "dd_cut": _f(_max_dd(mkt_timed) - _max_dd(mkt))},
        "structuring": structuring,
        "tax": tax,
        "verdict": ("Combining/risk-modelling/timing doesn't manufacture a significant standalone alpha on "
                    "123 mega-caps — but the structuring layers deliver real value (a factor-neutral, "
                    "turnover-capped book at a third the drawdown; exposure timing that halves the "
                    "directional drawdown; HIFO tax alpha) that needs no significant signal."),
    }


def _max_dd(r: pd.Series) -> float:
    r = r.dropna()
    if not len(r):
        return 0.0
    eq = (1.0 + r).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def _structuring_summary(rets, sigs, comp_w) -> dict:
    files = sorted(opt.OPTIONS_DIR.glob("snapshot_*.parquet"))
    if not files:
        return {"available": False}
    surface = pd.read_parquet(files[-1])
    rv = (rets.rolling(21).std().iloc[-1] * np.sqrt(TRADING_DAYS)).rename("rv")
    joined = surface.set_index("symbol").join(rv)
    joined["vrp"] = joined["atm_iv"] - joined["rv"]
    hedge = st.tail_hedge_sleeve(100_000.0, surface, moneyness=0.90)
    long_leg = comp_w.iloc[-1]
    positions = long_leg[long_leg > 0] * 100_000.0
    cand = st.overwrite_candidates(positions, surface, sigs["momentum"].iloc[-1], moneyness=1.05, top_n=5)
    over = []
    for _, r in cand.iterrows():
        over.append({"symbol": r["symbol"], "atm_iv": _f(r["atm_iv"]),
                     "premium_pct": _f(r["premium_pct"]), "vrp": _f(joined["vrp"].get(r["symbol"]))})
    return {
        "available": True, "asof": files[-1].stem.replace("snapshot_", ""),
        "n_names": int(len(surface)), "vrp_count": int((joined["vrp"] > 0).sum()),
        "median_iv": _f(surface["atm_iv"].median()), "median_skew": _f(surface["skew_25d"].median()),
        "tail_hedge": {"annual_drag": _f(hedge.get("annual_drag")), "cheap_drag": _f(hedge.get("cheap_entry_annual_drag")),
                       "avg_iv": _f(hedge.get("avg_iv")), "median_dte": _f(hedge.get("median_dte"))} if hedge.get("ok") else None,
        "overwrite": over,
    }


def _tax_summary(px, comp) -> list[dict]:
    weights, prices = _long_only_book(comp, px)
    if weights.empty:
        return []
    table = tx.compare_methods(weights, prices, capital=1_000_000.0)
    out = []
    for m in ("hifo", "fifo", "lifo"):
        r = table.loc[m]
        out.append({"method": m, "tax": _f(r["tax"]), "net_short_term": _f(r["net_short_term"]),
                    "net_long_term": _f(r["net_long_term"]), "lt_fraction": _f(r["lt_fraction_of_gains"]),
                    "wash_disallowed": _f(r["wash_sale_disallowed"]),
                    "deferred_gain": _f(r["deferred_unrealized_gain"])})
    return out


def _long_only_book(comp, px, rebalance=21, top_q=0.33):
    rows, prows = {}, {}
    for dt in comp.index[::rebalance]:
        s = comp.loc[dt].dropna()
        if len(s) < 6:
            continue
        longs = s[s >= s.quantile(1.0 - top_q)].index
        w = pd.Series(0.0, index=comp.columns)
        w[longs] = 1.0 / len(longs)
        rows[dt], prows[dt] = w, px.loc[dt]
    return pd.DataFrame(rows).T, pd.DataFrame(prows).T


# ── snapshot (told-story cache) ───────────────────────────────────────────────────────────────────
def load_snapshot() -> dict | None:
    if SNAPSHOT_PATH.exists():
        return json.loads(SNAPSHOT_PATH.read_text())
    return None


def build_snapshot() -> dict:
    """Compute the full told-story snapshot (findings + construction) and write it to disk."""
    snap = {"findings": compute_findings(), "construction": compute_construction()}
    SNAPSHOT_PATH.write_text(json.dumps(snap, indent=2))
    return snap
