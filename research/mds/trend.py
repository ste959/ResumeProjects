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

TRADING_DAYS = 252

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
def backtest(prices: pd.DataFrame, total_prices: pd.DataFrame | None = None, enh: frozenset = frozenset(),
             *, lookbacks=(21, 63, 126, 252), carry_lb: int = 252, vol_window: int = 63,
             target_vol: float = 0.10, max_leverage: float = 3.0, rebalance: int = 21,
             cost_bps: float = 10.0, rf: pd.Series | None = None) -> dict:
    """Walk-forward long/short trend book. Every `rebalance` days, form target weights from the signal
    known as of the prior close (one-day lag — no look-ahead), hold them out-of-sample, and charge
    `cost_bps` on turnover. Returns the net daily series + the shared honest stat block."""
    rets = prices.pct_change()
    sig = signal_panel(prices, total_prices, enh, lookbacks, carry_lb)
    inv_vol = _inv_vol(rets, vol_window) if "voltarget" in enh else None
    crash = crash_scaler(rets) if "crash" in enh else None

    dates, cols = rets.index, rets.columns
    n = len(cols)
    net = pd.Series(0.0, index=dates)
    w_prev = np.zeros(n)
    start = max(max(lookbacks), carry_lb) + 1         # need enough history for the longest signal

    for t in range(start, len(rets), rebalance):
        s = np.nan_to_num(sig.iloc[t - 1].to_numpy(dtype=float))    # signal from the prior close
        if "voltarget" in enh:
            w = s * np.nan_to_num(inv_vol.iloc[t - 1].to_numpy(dtype=float))
        else:
            w = np.sign(s)                             # vanilla: ±1 per asset, equal gross
        gross = np.abs(w).sum()
        if gross > 0:
            w = w / gross                              # normalize to gross leverage 1
        if "portvol" in enh:                           # scale to a constant *portfolio* vol (correlation-aware)
            cov = rets.iloc[t - TRADING_DAYS:t].cov().to_numpy() * TRADING_DAYS
            pv = float(np.sqrt(max(w @ cov @ w, 0.0)))
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
        w_prev = w

    net = net.iloc[start:]
    return {**ev.stats(net, rf), "net": net}


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
        st = ev.stats(seg, rf) if len(seg) > 30 else {"sharpe": float("nan"), "max_drawdown": float("nan")}
        out.append({"regime": name, "start": start, "end": end,
                    "sharpe": st["sharpe"], "max_drawdown": st["max_drawdown"], "n_days": int(len(seg))})
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
