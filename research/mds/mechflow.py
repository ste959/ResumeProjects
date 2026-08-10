"""Mechanical-flow reversal — "trading the shadow of the machines."

A structural edge that isn't a forecast: leveraged & inverse ETFs **must** rebalance their exposure every
day to maintain constant leverage, and — the key fact — *every* leveraged/inverse ETF rebalances in the
**same direction as the day's move** (they all buy on up days, sell on down days). For a k-times fund on a
move r, the forced trade is `k·(k-1)·AUM·r`, and `k(k-1) > 0` for every k∉{0,1} (3x → 6, −3x → 12, 2x → 2).
This flow is **price-insensitive, mechanical, and concentrated near the close** — it pushes the closing
print past the information-fair value, and because there's no information behind it, the overshoot should
partially **revert overnight**.

The falsifiable, novel prediction: the overnight reversal should scale with **forced flow ÷ underlying
liquidity** — negligible in SPY (too liquid to move) but large in semis/Nasdaq names whose leveraged
complexes are huge relative to the underlying's own volume. And unlike a published anomaly, the *source*
of this edge (mechanical flow) **grows** as markets get more passive/systematic — a durability thesis we
test with the decay monitor.

AUM figures are approximate (illustrative magnitudes; the relative ordering is what the signal uses). Pure
NumPy/pandas; trades overnight (close→open), so it uses a dedicated backtest, judged on the shared
`evaluation.py` stick.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import stats as st

TRADING_DAYS = 252

# underlying → [(leveraged ETF, leverage k, approx AUM $B)]; AUM approximate, ordering is what matters.
LEVERAGED_COMPLEXES = {
    "QQQ":  [("TQQQ", 3, 25.0), ("SQQQ", -3, 4.0), ("QLD", 2, 5.0), ("QID", -2, 0.4)],
    "SOXX": [("SOXL", 3, 12.0), ("SOXS", -3, 0.9)],
    "SPY":  [("UPRO", 3, 3.5), ("SPXU", -3, 0.9), ("SPXL", 3, 4.0), ("SPXS", -3, 0.7), ("SSO", 2, 4.5), ("SDS", -2, 0.7)],
    "IWM":  [("TNA", 3, 4.0), ("TZA", -3, 0.5)],
    "TLT":  [("TMF", 3, 4.0), ("TMV", -3, 0.4)],
    "XLF":  [("FAS", 3, 2.0), ("FAZ", -3, 0.2)],
    "DIA":  [("UDOW", 3, 1.0), ("SDOW", -3, 0.5)],
    "EEM":  [("EDC", 3, 0.3), ("EDZ", -3, 0.2)],
    "XLE":  [("ERX", 2, 0.4), ("ERY", -2, 0.1)],
}


def forced_flow_coef(complexes: dict = LEVERAGED_COMPLEXES) -> pd.Series:
    """Per-underlying forced-rebalance coefficient Σ k(k-1)·AUM — the $ the leveraged complex must trade per
    1.0 of underlying return, all in the direction of the move. Higher = more mechanical close pressure."""
    return pd.Series({u: sum(k * (k - 1) * aum for _, k, aum in legs) for u, legs in complexes.items()})


def relative_flow(close: pd.DataFrame, volume: pd.DataFrame, complexes: dict = LEVERAGED_COMPLEXES,
                  adv_window: int = 63) -> pd.Series:
    """Forced flow relative to the underlying's own liquidity: coef ÷ dollar ADV. The structural intensity —
    small where the underlying is deep (SPY), large where the leveraged complex dwarfs the tape (semis)."""
    coef = forced_flow_coef(complexes)
    syms = [u for u in coef.index if u in close.columns]
    adv = (close[syms] * volume[syms]).rolling(adv_window).mean().iloc[-1] / 1e9   # $B/day
    return (coef[syms] / adv.replace(0, np.nan)).dropna()


def overnight_returns(open_: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    """Close_t → open_{t+1} return, indexed at t (the position formed at close t earns it that night)."""
    return (open_.shift(-1) / close - 1.0)


def reversal_betas(close: pd.DataFrame, overnight: pd.DataFrame) -> pd.DataFrame:
    """For each underlying, regress the overnight return on the SAME day's close-to-close return. A negative
    beta = the day's move reverts overnight (the mechanical-overshoot signature). This is the *mechanism*
    test: the reversal (−beta) should be stronger where relative forced flow is larger."""
    daily = close.pct_change()
    rows = []
    for c in close.columns:
        df = pd.DataFrame({"x": daily[c], "y": overnight[c]}).dropna()
        if len(df) < 60:
            continue
        fit = st.ols(np.column_stack([np.ones(len(df)), df["x"].to_numpy()]), df["y"].to_numpy())
        rows.append({"underlying": c, "beta": round(float(fit["beta"][1]), 3),
                     "t_stat": round(float(fit["tstat"][1]), 2), "n": len(df)})
    return pd.DataFrame(rows).set_index("underlying")


def backtest_overnight(open_: pd.DataFrame, close: pd.DataFrame, volume: pd.DataFrame,
                       complexes: dict = LEVERAGED_COMPLEXES, vol_window: int = 21,
                       cost_bps: float = 3.0, rf: pd.Series | None = None) -> dict:
    """Cross-sectional, dollar-neutral overnight-reversal book, tilted toward high-relative-flow names.
    Each close: signal = −(vol-standardized daily return) × relative-flow weight, demeaned (dollar-neutral),
    gross-scaled; held overnight; `cost_bps` charged per unit turnover (a close→open round trip). Returns the
    net overnight series + diagnostics. Dollar-neutral strips the overnight equity premium, isolating the
    *mechanical* reversal."""
    syms = [u for u in complexes if u in close.columns]
    close, open_, volume = close[syms], open_[syms], volume[syms]
    daily = close.pct_change()
    overnight = overnight_returns(open_, close)
    rvol = daily.rolling(vol_window).std()
    rel = relative_flow(close, volume, complexes)                       # per-name structural intensity
    relw = pd.Series({s: rel.get(s, np.nan) for s in syms}).reindex(syms)

    z = -(daily / rvol.replace(0, np.nan))                              # reversal signal, vol-standardized
    raw = z.mul(relw, axis=1)                                           # tilt to high-forced-flow names
    W = raw.sub(raw.mean(axis=1), axis=0)                               # dollar-neutral
    gross = W.abs().sum(axis=1).replace(0, np.nan)
    W = W.div(gross, axis=0).fillna(0.0)

    pnl = (W * overnight).sum(axis=1)                                   # overnight P&L
    turn = (W - W.shift(1)).abs().sum(axis=1)
    net = (pnl - turn * cost_bps / 1e4).dropna()
    return {"net": net, "weights": W, "turnover_ann": round(float(turn.mean()) * TRADING_DAYS, 1),
            "relative_flow": relw}
