"""BTC/ETH statistical-arbitrage study — done with rigor, and reported honestly.

Pipeline: align close prices → an in-sample cointegration DIAGNOSTIC (Engle–Granger β, ADF,
OU half-life — a description of the window, not a tradeable rule) → a WALK-FORWARD, fully
out-of-sample backtest that re-estimates the hedge ratio on trailing data, freezes it, and
trades the resulting spread/z-score forward with realistic costs and a one-period execution
lag → report the metrics *and* a candid verdict on whether any edge survives.

Fitting β on the whole sample and "backtesting" it over that same window is in-sample leakage
that flatters the Sharpe; the walk-forward here is what makes the reported number honest.

The point is the methodology and the honesty, not a promise of profit: highly correlated
crypto majors rarely stay *cointegrated* net of fees, and the study is built to surface
that rather than hide it.
"""

from __future__ import annotations

import numpy as np

from . import backtest, sources
from .stats import engle_granger, half_life, rolling_zscore


def hysteresis_signal(z: np.ndarray, entry: float = 2.0, exit: float = 0.5) -> np.ndarray:
    """Mean-reversion position from a spread z-score.

    Short the spread when it is richly stretched (z > entry), long it when cheap
    (z < -entry), and flatten once it reverts inside ±exit. Hysteresis (entry ≠ exit)
    avoids churning around the threshold.
    """
    pos = np.zeros(len(z))
    cur = 0.0
    for t in range(len(z)):
        zt = z[t]
        if not np.isnan(zt):
            if cur == 0.0:
                if zt > entry:
                    cur = -1.0
                elif zt < -entry:
                    cur = 1.0
            elif abs(zt) < exit:
                cur = 0.0
        pos[t] = cur
    return pos


def walk_forward_backtest(y: np.ndarray, x: np.ndarray, window: int, entry: float, exit: float,
                          cost_bps: float, ppy: float, lookback: int, step: int) -> dict:
    """Out-of-sample pairs backtest — no look-ahead in the hedge ratio OR the spread stats.

    The whole point of pairs trading is that the hedge ratio is UNKNOWN when you trade; fitting β
    on the full sample and then "backtesting" the resulting spread over that same window is
    in-sample and flatters the Sharpe. Here we walk forward: at each rebalance we re-estimate
    (α, β) by Engle–Granger on the trailing `lookback` bars, FREEZE them, and use them to form the
    spread and its P&L for the next `step` bars only. The z-score is a trailing rolling stat over
    that OOS spread, so entries never peek at the future either. Only the OOS region (from the
    first fitted block onward) is scored.
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    n = len(y)
    beta_path = np.full(n, np.nan)
    alpha_path = np.full(n, np.nan)
    for start in range(lookback, n, step):
        eg = engle_granger(y[start - lookback:start], x[start - lookback:start])
        end = min(start + step, n)
        beta_path[start:end] = eg["beta"]
        alpha_path[start:end] = eg["alpha"]

    valid = ~np.isnan(beta_path)
    if not valid.any():
        return {**backtest.run(np.zeros(1), np.zeros(1), cost_bps=cost_bps, periods_per_year=ppy),
                "oos_observations": 0}

    spread = y - (alpha_path + beta_path * x)      # OOS spread (NaN before the first block)
    z = rolling_zscore(spread, window)
    position = hysteresis_signal(z, entry, exit)   # NaN z ⇒ flat, so it self-warms-up

    ret_y = np.diff(y, prepend=y[0])
    ret_x = np.diff(x, prepend=x[0])
    spread_ret = ret_y - np.nan_to_num(beta_path) * ret_x  # frozen β for each period

    first = int(np.argmax(valid))                  # first out-of-sample bar
    bt = backtest.run(spread_ret[first:], position[first:], cost_bps=cost_bps, periods_per_year=ppy)
    bt["oos_observations"] = int(n - first)
    return bt


def run(products=("BTC-USD", "ETH-USD"), granularity: int = 3600, pages: int = 6,
        window: int = 48, entry: float = 2.0, exit: float = 0.5, cost_bps: float = 2.0,
        lookback: int = 480, step: int = 48, refresh: bool = False) -> dict:
    px = sources.aligned_closes(list(products), granularity, pages, refresh)
    y = np.log(px[products[0]].to_numpy())
    x = np.log(px[products[1]].to_numpy())

    # In-sample DIAGNOSTIC only: describes whether a stable mean-reverting combination exists over
    # the whole window. It is NOT the tradeable signal — the backtest below is the OOS one.
    eg = engle_granger(y, x)
    spread = eg["spread"]
    hl = half_life(spread)
    ret_y = np.diff(y, prepend=y[0])
    ret_x = np.diff(x, prepend=x[0])
    corr = float(np.corrcoef(ret_y[1:], ret_x[1:])[0, 1])

    ppy = (365 * 24 * 3600) / granularity
    bt = walk_forward_backtest(y, x, window, entry, exit, cost_bps, ppy, lookback, step)

    return {
        "products": list(products),
        "observations": int(len(y)),
        "granularity_s": granularity,
        "return_correlation": corr,
        "hedge_ratio_beta": eg["beta"],       # full-sample diagnostic β (not used by the OOS bt)
        "adf_stat": eg["adf_stat"],           # in-sample cointegration diagnostic
        "coint_crit": eg["crit"],
        "cointegrated_5pct": eg["cointegrated_5pct"],
        "half_life_periods": hl,
        "walk_forward": {"lookback": lookback, "step": step},
        "backtest": bt,                       # OUT-OF-SAMPLE, walk-forward
        "verdict": _verdict(eg, bt),
    }


def _verdict(eg: dict, bt: dict) -> str:
    # bt is the OUT-OF-SAMPLE walk-forward result: β re-fit on trailing data, never on the block
    # it trades. That is the honest number.
    if not eg["cointegrated_5pct"]:
        if bt["sharpe"] >= 1.0:
            return (f"Not cointegrated at 5% in-sample, yet the walk-forward OOS Sharpe is {bt['sharpe']:.2f} "
                    f"over {bt['num_trades']} trades — treat with suspicion: without stable cointegration "
                    "the reversion premise is shaky, so this is likely regime-luck, not a durable edge.")
        return ("No stable cointegration at the 5% level and no out-of-sample edge — the pairs "
                "assumption does not hold over this window. An honest negative result.")
    if bt["sharpe"] < 1.0:
        return (f"Cointegrated, but the walk-forward OOS net Sharpe is only {bt['sharpe']:.2f} after "
                f"{bt['num_trades']} trades — the edge does not clearly survive costs.")
    return (f"Cointegrated with a walk-forward OOS net Sharpe of {bt['sharpe']:.2f} — promising, but "
            "still validate against realistic latency/fees and on a fresh window before believing it.")
