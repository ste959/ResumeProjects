"""BTC/ETH statistical-arbitrage study — done with rigor, and reported honestly.

Pipeline: align close prices → test for cointegration (Engle–Granger) → build the
mean-reverting spread and its z-score → generate a hysteresis mean-reversion signal →
backtest with realistic costs and a one-period execution lag → report the metrics *and*
a candid verdict on whether any edge survives.

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


def run(products=("BTC-USD", "ETH-USD"), granularity: int = 3600, pages: int = 6,
        window: int = 48, entry: float = 2.0, exit: float = 0.5, cost_bps: float = 2.0,
        refresh: bool = False) -> dict:
    px = sources.aligned_closes(list(products), granularity, pages, refresh)
    y = np.log(px[products[0]].to_numpy())
    x = np.log(px[products[1]].to_numpy())

    eg = engle_granger(y, x)
    beta = eg["beta"]
    spread = eg["spread"]
    hl = half_life(spread)
    z = rolling_zscore(spread, window)
    position = hysteresis_signal(z, entry, exit)

    ret_y = np.diff(y, prepend=y[0])
    ret_x = np.diff(x, prepend=x[0])
    spread_ret = ret_y - beta * ret_x  # P&L of a unit long-spread position
    corr = float(np.corrcoef(ret_y[1:], ret_x[1:])[0, 1])

    ppy = (365 * 24 * 3600) / granularity
    bt = backtest.run(spread_ret, position, cost_bps=cost_bps, periods_per_year=ppy)

    return {
        "products": list(products),
        "observations": int(len(y)),
        "granularity_s": granularity,
        "return_correlation": corr,
        "hedge_ratio_beta": beta,
        "adf_stat": eg["adf_stat"],
        "coint_crit": eg["crit"],
        "cointegrated_5pct": eg["cointegrated_5pct"],
        "half_life_periods": hl,
        "backtest": bt,
        "verdict": _verdict(eg, bt),
    }


def _verdict(eg: dict, bt: dict) -> str:
    if not eg["cointegrated_5pct"]:
        if bt["sharpe"] >= 1.0:
            return (f"RED FLAG: the in-sample Sharpe looks strong ({bt['sharpe']:.2f}), but the pair is "
                    "NOT cointegrated at 5% — the mean-reversion premise fails, so this is almost "
                    "certainly spurious/overfit and would not survive out-of-sample. Do not trade it.")
        return ("No stable cointegration at the 5% level and no in-sample edge — the pairs "
                "assumption does not hold over this window.")
    if bt["sharpe"] < 1.0:
        return (f"Cointegrated, but the signal's net Sharpe is only {bt['sharpe']:.2f} after "
                f"{bt['num_trades']} trades — the edge does not clearly survive costs.")
    return (f"Cointegrated with a net Sharpe of {bt['sharpe']:.2f} in-sample — promising, but "
            "validate out-of-sample and against realistic latency/fees before believing it.")
