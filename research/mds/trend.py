"""Enhanced multi-asset trend-following (time-series momentum) — built to *earn its Sharpe honestly*.

Vanilla trend captures a **premium** (you're paid to bear trend risk). This module layers the
enhancements that historically improved trend's *risk-adjusted* capture and diversified its known
failure modes, each addable independently so an **ablation** can show what actually earned its keep:

  1. **Breadth** — a broad, diversified cross-asset universe (Grinold–Kahn: IR ≈ IC·√breadth).
  2. **Multi-timescale, risk-adjusted signal** — trend measured in units of its own vol and saturated
     (tanh), ensembled over 1–12-month horizons, instead of one fragile lookback and a binary sign.
  3. **Volatility targeting** — size each leg inversely to its vol; the biggest driver of trend's
     historical Sharpe (Harvey et al. 2018), and a portfolio-level constant-vol overlay on top.
  4. **Carry** — a *diversifying* second premium: trailing income (distribution) yield, blended with
     trend. The closest thing here to alpha-over-premium (a distinct return source, not more of the same).
  5. **Crash protection** — de-risk when cross-asset vol spikes, targeting trend's momentum-crash tail
     (Daniel–Moskowitz 2016).
  6. **Cross-sectional overlay** — TS trend (each asset vs. its own past) + XS momentum (assets vs. each
     other) are distinct bets that diversify.

Everything is walk-forward and cost-aware, and judged by the **same** `evaluation.py` harness (excess-
of-cash Sharpe, HAC t, bootstrap CI, tail metrics, PBO/DSR gauntlet) as the allocation study. Pure
NumPy/pandas — no I/O; `run_trend.py` feeds it real ETF data. The honest expectation is a *modest* IR
lift, not a miracle: a trend book that suddenly Sharpes >2 after six tweaks is overfit, and the gauntlet
+ sensitivity sweep exist to say so.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import evaluation as ev
from . import stats as st

TRADING_DAYS = 252

# Map each market to an economic sleeve, for P&L / exposure attribution.
SLEEVES = {
    "SPY": "Equity", "EFA": "Equity", "EEM": "Equity", "IWM": "Equity", "VNQ": "Equity",
    "SHY": "Rates", "IEF": "Rates", "TLT": "Rates",
    "LQD": "Credit", "HYG": "Credit",
    "DBC": "Commodity", "GLD": "Commodity", "UUP": "USD",
}

# ── Breadth: a diversified cross-asset universe (liquid ETF proxies) ───────────────────────────────
# Equity by region, the Treasury curve, credit, real assets, and the dollar — deliberately spanning
# asset classes so trends are as independent as free daily ETF data allows.
UNIVERSE = {
    "SPY": "US equity", "EFA": "Intl equity", "EEM": "EM equity", "IWM": "US small-cap",
    "SHY": "UST 1-3y", "IEF": "UST 7-10y", "TLT": "UST 20y+",
    "LQD": "IG credit", "HYG": "High yield",
    "DBC": "Commodities", "GLD": "Gold", "VNQ": "REITs", "UUP": "US dollar",
}

# The enhancement flags (see the module docstring); a `backtest` takes the subset that's enabled.
ALL_ENH = frozenset({"voltarget", "multiscale", "portvol", "carry", "crash", "xs"})

# Cumulative ablation: add one enhancement at a time so each stage's contribution is visible.
ABLATION = [
    ("vanilla (1-lookback sign)", frozenset()),
    ("+ vol-targeting", frozenset({"voltarget"})),
    ("+ multi-timescale", frozenset({"voltarget", "multiscale"})),
    ("+ portfolio vol-target", frozenset({"voltarget", "multiscale", "portvol"})),
    ("+ carry blend", frozenset({"voltarget", "multiscale", "portvol", "carry"})),
    ("+ crash-protection", frozenset({"voltarget", "multiscale", "portvol", "carry", "crash"})),
    ("+ cross-sectional", ALL_ENH),
]


# ── Signals (all causal: every value at date t uses only data through t) ──────────────────────────
def _xs_z(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score (standardize across assets each date) — puts different signals on a
    comparable scale so a trend+carry blend is meaningful."""
    mu = df.mean(axis=1)
    sd = df.std(axis=1).replace(0.0, np.nan)
    return df.sub(mu, axis=0).div(sd, axis=0).fillna(0.0)


def trend_score(prices: pd.DataFrame, lookbacks=(21, 63, 126, 252), k: float = 1.0,
                multiscale: bool = True) -> pd.DataFrame:
    """Trend signal per asset. `multiscale=True`: risk-adjusted trend (cumulative return over the
    horizon ÷ its vol — a t-stat of the trend), saturated with tanh and averaged over horizons, giving
    a smooth signal in ~[-1, 1]. `multiscale=False`: the vanilla baseline — the sign of the single
    longest-lookback return (binary, whipsaw-prone)."""
    rets = prices.pct_change()
    if not multiscale:
        L = lookbacks[-1]
        return np.sign(prices / prices.shift(L) - 1.0)
    sig = None
    for L in lookbacks:
        cum = prices / prices.shift(L) - 1.0
        vol = (rets.rolling(L).std() * np.sqrt(L)).replace(0.0, np.nan)   # trend vol over the horizon
        s = np.tanh(k * (cum / vol))
        sig = s if sig is None else sig + s
    return (sig / len(lookbacks)).fillna(0.0)


def carry_score(total_prices: pd.DataFrame, price_prices: pd.DataFrame, lookback: int = 252) -> pd.DataFrame:
    """Trailing income (distribution) yield ≈ total-return minus price-return over the lookback,
    annualized — a cross-asset **carry** proxy from price data alone. Total-return and price-only series
    differ exactly by distributions, so the gap is the yield an asset throws off; ≈0 for non-distributing
    assets (gold, the dollar ETF), materially positive for bonds/credit/high-dividend equity."""
    tot = total_prices / total_prices.shift(lookback) - 1.0
    pr = price_prices / price_prices.shift(lookback) - 1.0
    return ((tot - pr) * (TRADING_DAYS / lookback)).fillna(0.0)


def xs_momentum(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Cross-sectional (12–1) momentum: trailing return skipping the last month (to avoid short-term
    reversal), standardized across assets → a roughly market-neutral rotation signal. Distinct from the
    time-series trend (each asset vs. its own history) and diversifies it."""
    mom = prices.shift(skip) / prices.shift(lookback) - 1.0
    return _xs_z(mom)


def crash_scaler(rets: pd.DataFrame, fast: int = 21, slow: int = 126, floor: float = 0.4) -> pd.Series:
    """Risk-off multiplier in [floor, 1]: cut gross exposure when cross-asset realized vol spikes above
    its own trailing level (fast average > slow average). Causal (trailing windows only). Targets
    trend's momentum-crash failure mode — the sharp reversals where a fully-invested trend book bleeds."""
    v = rets.abs().mean(axis=1)                       # cross-asset mean |move| ~ a market-vol proxy
    ratio = (v.rolling(slow).mean() / v.rolling(fast).mean())   # <1 when recent vol > long-run vol
    return ratio.clip(lower=floor, upper=1.0).fillna(1.0)


def _inv_vol(rets: pd.DataFrame, window: int = 63, floor: float = 0.05) -> pd.DataFrame:
    """1/σ per asset (annualized vol, floored) — the vol-targeting weight before normalization."""
    vol = (rets.rolling(window).std() * np.sqrt(TRADING_DAYS)).clip(lower=floor)
    return 1.0 / vol


# ── Combined signal panel ─────────────────────────────────────────────────────────────────────────
def signal_panel(prices: pd.DataFrame, total_prices: pd.DataFrame | None, enh: frozenset,
                 lookbacks=(21, 63, 126, 252), carry_lb: int = 252) -> pd.DataFrame:
    """The combined per-asset directional signal for an enhancement set (all causal)."""
    trend = trend_score(prices, lookbacks, multiscale=("multiscale" in enh))
    combined = trend
    if "carry" in enh and total_prices is not None:
        carry = carry_score(total_prices.reindex_like(prices), prices, carry_lb)
        combined = 0.5 * _xs_z(trend) + 0.5 * _xs_z(carry)       # blend two comparable-scaled signals
    if "xs" in enh:
        combined = 0.5 * combined + 0.5 * xs_momentum(prices)
    return combined


# ── Walk-forward backtest ─────────────────────────────────────────────────────────────────────────
def _run(prices: pd.DataFrame, total_prices: pd.DataFrame | None, enh: frozenset, *,
         lookbacks, carry_lb, vol_window, target_vol, max_leverage, rebalance, cost_bps,
         portvol_mode: str | None) -> tuple[pd.Series, pd.DataFrame, dict]:
    """The walk-forward engine. Returns (net daily series, held-weights panel, diagnostics). The
    weights panel powers the P&L/exposure attribution; `portvol_mode` selects the vol-scaling
    mechanism (`none` / `diag` / `cov`) so the decomposition can isolate each one."""
    rets = prices.pct_change()
    sig = signal_panel(prices, total_prices, enh, lookbacks, carry_lb)
    inv_vol = _inv_vol(rets, vol_window) if "voltarget" in enh else None
    crash = crash_scaler(rets) if "crash" in enh else None
    mode = portvol_mode if portvol_mode is not None else ("cov" if "portvol" in enh else "none")

    dates, cols = rets.index, rets.columns
    n = len(cols)
    net = pd.Series(0.0, index=dates)
    W = pd.DataFrame(0.0, index=dates, columns=cols)  # weight actually held each day (for attribution)
    w_prev = np.zeros(n)
    start = max(max(lookbacks), carry_lb) + 1         # need enough history for the longest signal
    grosses, turns = [], []

    for t in range(start, len(rets), rebalance):
        s = np.nan_to_num(sig.iloc[t - 1].to_numpy(dtype=float))    # signal from the prior close
        if "voltarget" in enh:
            w = s * np.nan_to_num(inv_vol.iloc[t - 1].to_numpy(dtype=float))
        else:
            w = np.sign(s)                             # vanilla: ±1 per asset, equal gross
        gross = np.abs(w).sum()
        if gross > 0:
            w = w / gross                              # normalize to gross leverage 1
        if mode != "none":                             # scale toward a constant *portfolio* vol
            win = rets.iloc[t - TRADING_DAYS:t]
            if mode == "cov":                          # full covariance → correlation-aware
                pv = float(np.sqrt(max(w @ (win.cov().to_numpy() * TRADING_DAYS) @ w, 0.0)))
            else:                                      # diagonal only → vol-timing, correlation-blind
                pv = float(np.sqrt(max(np.sum(w * w * (win.var().to_numpy() * TRADING_DAYS)), 0.0)))
            if pv > 0:
                w = w * (target_vol / pv)
        if "crash" in enh:
            w = w * float(crash.iloc[t - 1])
        g = np.abs(w).sum()                            # honest leverage cap
        if g > max_leverage:
            w = w * (max_leverage / g)

        block = rets.iloc[t:t + rebalance].to_numpy()
        port = block @ w
        turn = float(np.abs(w - w_prev).sum())         # turnover vs. the previous target book
        if len(port):
            port[0] -= turn * cost_bps / 1e4           # charge cost on the rebalance day
            net.iloc[t:t + len(port)] = port
            W.iloc[t:t + len(port)] = w
        grosses.append(float(np.abs(w).sum()))
        turns.append(turn)
        w_prev = w

    net, W = net.iloc[start:], W.iloc[start:]
    diag = {"avg_gross": round(float(np.mean(grosses)), 2) if grosses else 0.0,
            "turnover_ann": round(float(np.mean(turns)) * (TRADING_DAYS / rebalance), 1) if turns else 0.0}
    return net, W, diag


def backtest(prices: pd.DataFrame, total_prices: pd.DataFrame | None = None, enh: frozenset = frozenset(),
             *, lookbacks=(21, 63, 126, 252), carry_lb: int = 252, vol_window: int = 63,
             target_vol: float = 0.10, max_leverage: float = 3.0, rebalance: int = 21,
             cost_bps: float = 10.0, portvol_mode: str | None = None, rf: pd.Series | None = None) -> dict:
    """Walk-forward long/short trend book: every `rebalance` days form target weights from the signal
    known at the prior close (one-day lag — no look-ahead), hold out-of-sample, charge `cost_bps` on
    turnover. Returns the shared honest stat block + avg gross leverage + annual turnover + the net series."""
    net, _, diag = _run(prices, total_prices, enh, lookbacks=lookbacks, carry_lb=carry_lb,
                        vol_window=vol_window, target_vol=target_vol, max_leverage=max_leverage,
                        rebalance=rebalance, cost_bps=cost_bps, portvol_mode=portvol_mode)
    return {**ev.stats(net, rf), **diag, "net": net}


# ── Ablation, regime robustness, sensitivity ──────────────────────────────────────────────────────
def ablation(prices: pd.DataFrame, total_prices: pd.DataFrame | None = None,
             rf: pd.Series | None = None, **kw) -> dict:
    """Add each enhancement in turn and report the stat block at every stage — so you can *see* which
    knob earned its keep and which was overfit. The ablation stages are themselves a strategy SET, so
    the same selection-aware gauntlet applies (backtesting 7 variants on one sample IS multiple testing)."""
    rows, nets = [], {}
    for name, enh in ABLATION:
        r = backtest(prices, total_prices, enh, rf=rf, **kw)
        nets[name] = r.pop("net")
        rows.append({"stage": name, "enh": sorted(enh), **r})
    gauntlet = ev.gauntlet(nets, rf)
    return {"stages": rows, "gauntlet": gauntlet, "nets": nets}


def regime_study(prices: pd.DataFrame, regimes: list[tuple[str, str, str]],
                 total_prices: pd.DataFrame | None = None, enh: frozenset = ALL_ENH,
                 rf: pd.Series | None = None, **kw) -> list[dict]:
    """Robustness of the full system across calendar sub-periods — one 6-year path proves nothing.
    Runs the walk-forward once, then slices the net series into named regimes and reports each one's
    excess Sharpe and drawdown."""
    net = backtest(prices, total_prices, enh, rf=rf, **kw)["net"]
    out = []
    for name, start, end in regimes:
        seg = net.loc[start:end]
        # Named seg_stats, not st: `st` is the module alias for the stats library (from . import stats
        # as st) used elsewhere in this file — rebinding it here shadowed the import and was a latent bug.
        seg_stats = ev.stats(seg, rf) if len(seg) > 30 else {"sharpe": float("nan"), "max_drawdown": float("nan")}
        out.append({"regime": name, "start": start, "end": end,
                    "sharpe": seg_stats["sharpe"], "max_drawdown": seg_stats["max_drawdown"], "n_days": int(len(seg))})
    return out


def sensitivity(prices: pd.DataFrame, total_prices: pd.DataFrame | None = None,
                rf: pd.Series | None = None, enh: frozenset = ALL_ENH,
                rebalances=(21, 63), costs=(5.0, 10.0, 25.0), target_vols=(0.08, 0.10, 0.15)) -> list[dict]:
    """Sweep the arbitrary choices (rebalance frequency, cost, vol target) and report the full system's
    Sharpe and HAC t at each — anti-p-hacking: a real effect is stable across the grid, not a knife-edge."""
    out = []
    for rb in rebalances:
        for c in costs:
            for tv in target_vols:
                r = backtest(prices, total_prices, enh, rebalance=rb, cost_bps=c, target_vol=tv, rf=rf)
                out.append({"rebalance": rb, "cost_bps": c, "target_vol": tv,
                            "sharpe": r["sharpe"], "hac_t": r["hac_t"], "max_drawdown": r["max_drawdown"]})
    return out


# ── Diagnostics: attribute the numbers, don't just report them ────────────────────────────────────
def voltarget_decomposition(prices: pd.DataFrame, total_prices: pd.DataFrame | None = None,
                            rf: pd.Series | None = None,
                            base: frozenset = frozenset({"voltarget", "multiscale"}), **kw) -> list[dict]:
    """Split the portfolio-vol overlay into its three mechanisms, holding the signal fixed:
      • `none` — constant gross (the signal alone, no vol scaling);
      • `diag` — scale to a constant vol using only the **diagonal** (variance) → vol-*timing*, correlation-blind;
      • `cov`  — scale using the full covariance → adds **correlation-awareness** on top.
    The Sharpe gap none→diag is the vol-timing contribution; diag→cov is the correlation contribution — so the
    single suspicious ablation jump gets attributed to a mechanism instead of a label."""
    modes = [("none", "constant gross (signal only)"),
             ("diag", "+ scalar vol-target (timing, no corr)"),
             ("cov", "+ covariance vol-target (adds corr)")]
    out = []
    for mode, label in modes:
        r = backtest(prices, total_prices, base, rf=rf, portvol_mode=mode, **kw)
        out.append({"mode": mode, "label": label, "sharpe": r["sharpe"], "ann_vol": r["ann_vol"],
                    "max_drawdown": r["max_drawdown"], "avg_gross": r["avg_gross"]})
    return out


def loo_ablation(prices: pd.DataFrame, total_prices: pd.DataFrame | None = None,
                 rf: pd.Series | None = None, **kw) -> list[dict]:
    """Leave-one-out: from the full system, remove ONE enhancement at a time. Order-independent, so it
    answers each enhancement's marginal value *holding the others fixed* — the honest question the
    cumulative ablation can't (its per-step deltas depend on the order things were added). `delta` =
    Sharpe(without it) − Sharpe(full): negative ⇒ the enhancement helps, positive ⇒ it hurts."""
    full = backtest(prices, total_prices, ALL_ENH, rf=rf, **kw)
    rows = [{"variant": "full system", "removed": "—", "sharpe": full["sharpe"], "delta": 0.0,
             "avg_gross": full["avg_gross"]}]
    for e in sorted(ALL_ENH):
        r = backtest(prices, total_prices, ALL_ENH - {e}, rf=rf, **kw)
        rows.append({"variant": f"− {e}", "removed": e, "sharpe": r["sharpe"],
                     "delta": round(r["sharpe"] - full["sharpe"], 3), "avg_gross": r["avg_gross"]})
    return rows


def _by_sleeve(per_asset: pd.Series) -> pd.Series:
    """Group a per-asset series into economic sleeves (Equity / Rates / Credit / Commodity / USD)."""
    return per_asset.groupby(lambda a: SLEEVES.get(a, "Other")).sum()


def attribution(prices: pd.DataFrame, total_prices: pd.DataFrame | None = None, enh: frozenset = ALL_ENH,
                rf: pd.Series | None = None, regimes: list[tuple[str, str, str]] | None = None, **kw) -> dict:
    """Per-sleeve P&L and exposure attribution — what the book actually *did*. Decomposes net return into
    each asset's daily contribution (wᵢ·rᵢ), groups into sleeves, and reports average net & gross
    exposure per sleeve, plus the per-sleeve P&L within each named regime (so '2022' becomes a checkable
    mechanism, not a claim). Contributions are arithmetic (they sum to the gross-of-cost net return)."""
    net, W, diag = _run(prices, total_prices, enh, lookbacks=kw.get("lookbacks", (21, 63, 126, 252)),
                        carry_lb=kw.get("carry_lb", 252), vol_window=kw.get("vol_window", 63),
                        target_vol=kw.get("target_vol", 0.10), max_leverage=kw.get("max_leverage", 3.0),
                        rebalance=kw.get("rebalance", 21), cost_bps=kw.get("cost_bps", 10.0),
                        portvol_mode=kw.get("portvol_mode", None))
    rets = prices.pct_change().reindex(W.index)
    contrib = rets * W                                # daily P&L contribution per asset
    per_asset = contrib.sum()
    result = {
        "per_sleeve": _by_sleeve(per_asset).sort_values(ascending=False),
        "net_exposure": _by_sleeve(W.mean()),         # avg signed weight per sleeve (net long/short)
        "gross_exposure": _by_sleeve(W.abs().mean()),
        "avg_gross": diag["avg_gross"], "turnover_ann": diag["turnover_ann"], "net": net,
    }
    if regimes:
        result["regime_sleeve"] = {name: _by_sleeve(contrib.loc[start:end].sum()).sort_values(ascending=False)
                                   for name, start, end in regimes}
    return result


def factor_betas(net: pd.Series, factors: pd.DataFrame, rf: pd.Series | None = None) -> dict:
    """Regress the book's EXCESS return on factor returns (+ intercept) — is the 'premium' just disguised
    beta? Returns annualized alpha and its t-stat, each factor's beta and t, and R². A genuine diversifier
    has a small/near-zero equity+bond beta and its 'crisis convexity' shows up as low beta in the stress
    slice, not a static short-duration bet. (Classical OLS SEs via `mds/stats.ols`.)"""
    ex = pd.Series(ev.excess(net, rf), index=net.index)
    df = ex.to_frame("y").join(factors, how="inner").dropna()
    if len(df) < 30:
        return {"alpha_ann": 0.0, "alpha_t": 0.0, "betas": {}, "beta_t": {}, "r2": 0.0, "n": len(df)}
    fcols = list(factors.columns)
    X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy() for c in fcols])
    fit = st.ols(X, df["y"].to_numpy())
    b, tt = fit["beta"], fit["tstat"]
    resid = fit["resid"]
    y = df["y"].to_numpy()
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else 0.0
    return {"alpha_ann": round(float(b[0]) * TRADING_DAYS, 4), "alpha_t": round(float(tt[0]), 2),
            "betas": {c: round(float(b[i + 1]), 3) for i, c in enumerate(fcols)},
            "beta_t": {c: round(float(tt[i + 1]), 2) for i, c in enumerate(fcols)},
            "r2": round(r2, 3), "n": len(df)}
