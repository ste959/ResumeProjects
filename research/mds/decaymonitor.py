"""Alpha-decay, crowding & capacity monitor — the *alpha lifecycle*, which is the part institutions
actually manage.

No edge is permanent. A multi-strat doesn't survive on one durable signal; it runs a factory of many
small, individually-decaying edges and wins by **detecting decay early, sizing to capacity, and retiring
edges before they bleed.** This module is that control system: given a strategy's realized returns (and,
optionally, a factor to test crowding against), it reports whether the edge is *strengthening, stable, or
dying*, how fast, and whether it's getting crowded into a known factor.

Answers the only honest question about any backtested edge — "will it still be here in six months?" — with
evidence instead of hope. Operates on any `engine.StrategyResult.net`; capacity reuses `engine.capacity_curve`.
Pure NumPy/pandas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import evaluation as ev
from . import stats as st

TRADING_DAYS = 252


def _sharpe(ex: np.ndarray) -> float:
    sd = ex.std()
    return float(ex.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0


def bucketed_sharpe(net: pd.Series, n_buckets: int = 6, rf: pd.Series | None = None) -> pd.DataFrame:
    """Split the sample into `n_buckets` contiguous sub-periods and report each one's excess Sharpe — the
    raw material for seeing whether performance is trending down over time (the signature of decay)."""
    ex = pd.Series(ev.excess(net, rf), index=net.index).dropna()
    edges = np.array_split(np.arange(len(ex)), n_buckets)
    rows = []
    for i, e in enumerate(edges):
        if len(e) < 10:
            continue
        seg = ex.iloc[e]
        rows.append({"bucket": i, "start": str(seg.index[0].date()), "end": str(seg.index[-1].date()),
                     "sharpe": round(_sharpe(seg.to_numpy()), 3), "n_days": len(seg)})
    return pd.DataFrame(rows)


def performance_trend(net: pd.Series, n_buckets: int = 6, rf: pd.Series | None = None) -> dict:
    """Regress bucketed Sharpe on time. A negative, significant slope = the edge is decaying; the linear
    fit also gives a rough 'sessions until the edge reaches zero'."""
    b = bucketed_sharpe(net, n_buckets, rf)
    if len(b) < 3:
        return {"slope": 0.0, "t_stat": 0.0, "buckets": b}
    x = b["bucket"].to_numpy(dtype=float)
    y = b["sharpe"].to_numpy(dtype=float)
    fit = st.ols(np.column_stack([np.ones(len(x)), x]), y)
    slope, t = float(fit["beta"][1]), float(fit["tstat"][1])
    bucket_len = len(net) / n_buckets
    sessions_to_zero = None
    if slope < 0:                                        # extrapolate the decline to Sharpe = 0
        cur = float(fit["beta"][0] + slope * (len(b) - 1))
        sessions_to_zero = int(max(0.0, cur / -slope) * bucket_len) if cur > 0 else 0
    return {"slope": round(slope, 3), "t_stat": round(t, 2), "sessions_to_zero": sessions_to_zero, "buckets": b}


def half_life(net: pd.Series, n_buckets: int = 8, rf: pd.Series | None = None) -> float:
    """Decay half-life in trading days, from a log-linear fit to the (positive) bucketed Sharpe. `inf` if
    the edge isn't decaying (flat/rising)."""
    b = bucketed_sharpe(net, n_buckets, rf)
    y = b["sharpe"].to_numpy(dtype=float)
    if len(y) < 3 or (y <= 0).all():
        return float("inf")
    ly = np.log(np.clip(y, 1e-3, None))
    x = np.arange(len(y), dtype=float)
    fit = st.ols(np.column_stack([np.ones(len(x)), x]), ly)
    k = float(fit["beta"][1])                            # per-bucket decay rate
    if k >= 0:
        return float("inf")
    return float(np.log(2) / (-k) * (len(net) / n_buckets))


def crowding_trend(net: pd.Series, factor: pd.Series, window: int = 126) -> dict:
    """Is the strategy drifting into a crowded factor? Rolling correlation of the strategy to `factor`,
    then its time trend — a *rising* correlation means the edge increasingly looks like (and competes
    with) a known factor everyone else trades."""
    df = pd.DataFrame({"s": net, "f": factor}).dropna()
    roll = df["s"].rolling(window).corr(df["f"]).dropna()
    if len(roll) < 30:
        return {"corr_now": float("nan"), "corr_slope": 0.0, "t_stat": 0.0}
    x = np.arange(len(roll), dtype=float)
    fit = st.ols(np.column_stack([np.ones(len(x)), x]), roll.to_numpy())
    return {"corr_now": round(float(roll.iloc[-1]), 3), "corr_slope": round(float(fit["beta"][1]) * len(roll), 3),
            "t_stat": round(float(fit["tstat"][1]), 2)}


def ic_decay(ic: pd.Series, n_buckets: int = 6) -> dict:
    """Same decay test for a signal's information coefficient over time (for signal-based edges)."""
    ic = ic.dropna()
    edges = np.array_split(np.arange(len(ic)), n_buckets)
    means = [float(ic.iloc[e].mean()) for e in edges if len(e) >= 5]
    if len(means) < 3:
        return {"first": float("nan"), "last": float("nan"), "slope": 0.0}
    x = np.arange(len(means), dtype=float)
    fit = st.ols(np.column_stack([np.ones(len(x)), x]), np.array(means))
    return {"first": round(means[0], 4), "last": round(means[-1], 4),
            "slope": round(float(fit["beta"][1]), 4), "t_stat": round(float(fit["tstat"][1]), 2)}


def decay_report(net: pd.Series, rf: pd.Series | None = None, factor: pd.Series | None = None,
                 n_buckets: int = 6) -> dict:
    """The alpha-health verdict: overall vs. first-half vs. second-half Sharpe, the decay slope and its
    t-stat, the half-life, an optional crowding read, and a plain-English classification."""
    ex = pd.Series(ev.excess(net, rf), index=net.index).dropna()
    half = len(ex) // 2
    s_all, s1, s2 = _sharpe(ex.to_numpy()), _sharpe(ex.iloc[:half].to_numpy()), _sharpe(ex.iloc[half:].to_numpy())
    trend = performance_trend(net, n_buckets, rf)
    hl = half_life(net, max(n_buckets, 8), rf)
    crowd = crowding_trend(net, factor) if factor is not None else None

    decaying = trend["slope"] < 0 and abs(trend["t_stat"]) >= 1.0
    beta_dominated = crowd is not None and abs(crowd.get("corr_now", 0.0)) > 0.7 and crowd.get("corr_slope", 0.0) > 0
    if s1 > 0 and s2 <= 0:
        verdict = "DECAYED — the edge worked in the first half and is gone in the second"
    elif decaying and s2 < s1:
        verdict = "DECAYING — performance is trending down; size down / monitor closely"
    elif trend["slope"] > 0 and s2 >= s1:
        verdict = "ROBUST — no decay signature (performance stable-to-improving)"
    else:
        verdict = "STABLE — no clear decay, but the sample is short; keep watching"
    if beta_dominated:                                  # the crowding detector's key catch
        verdict = (f"BETA-DOMINATED — {crowd['corr_now']:+.2f} correlation to the factor and rising: this is "
                   f"market exposure wearing an alpha costume, not an independent edge. [{verdict}]")
    return {"sharpe_all": round(s_all, 3), "sharpe_first_half": round(s1, 3), "sharpe_second_half": round(s2, 3),
            "decay_slope": trend["slope"], "decay_t": trend["t_stat"],
            "sessions_to_zero": trend["sessions_to_zero"], "half_life_days": (None if hl == float("inf") else int(hl)),
            "crowding": crowd, "verdict": verdict, "buckets": trend["buckets"]}
