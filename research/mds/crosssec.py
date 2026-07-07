"""Cross-sectional equity signals + a dollar-neutral bar-level backtester.

Cross-sectional means a signal is RELATIVE across names each day (rank/z-score), not absolute
— the standard systematic-equities frame (Citadel EQR, AQR, Two Sigma). The backtester is
honest in the same way as the L2 engine, one domain up:

  * no look-ahead — a signal from data up to day t is traded into the day-t+1 return;
  * dollar-neutral, unit-gross weights (long the strong names, short the weak, net ~0);
  * turnover costs every rebalance (half-spread + fees) — the thing that decides whether a
    paper edge is real, and which favours low-turnover signals;
  * missing names are excluded from the cross-section that day rather than forward-filled to a
    fake price (free IEX has real gaps).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import alpaca_data as ad

TRADING_DAYS = 252


def returns_panel(field: str = "close"):
    """Return (price panel, log-return panel) as dates × symbols frames."""
    bars = ad.load_bars()
    px = ad.close_panel(bars, field).sort_index()
    rets = np.log(px).diff()
    return px, rets


def signals(px: pd.DataFrame, rets: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """A few classic cross-sectional signals, each a dates × symbols score (higher = long)."""
    logpx = np.log(px)
    return {
        # 12–1 month momentum: last ~12m return skipping the most recent month.
        "momentum": logpx.diff(252) - logpx.diff(21),
        # short-term reversal: last week's losers tend to bounce → negate the 5-day return.
        "reversal": -rets.rolling(5).sum(),
        # low-volatility: prefer calmer names → negate trailing vol.
        "low_vol": -rets.rolling(21).std(),
    }


def _xs_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score each day (demean and scale across symbols, excluding NaNs)."""
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0)


def backtest(signal: pd.DataFrame, rets: pd.DataFrame, cost_bps: float = 5.0) -> dict:
    """Backtest a cross-sectional signal as a dollar-neutral, unit-gross portfolio."""
    weights = _xs_zscore(signal)
    # Dollar-neutral, unit gross exposure: scale so the day's absolute weights sum to 1.
    gross_exposure = weights.abs().sum(axis=1).replace(0, np.nan)
    weights = weights.div(gross_exposure, axis=0).fillna(0.0)

    # Held one day: weights decided at t earn the t→t+1 return (no look-ahead).
    gross = (weights.shift(1) * rets).sum(axis=1, skipna=True)
    turnover = (weights - weights.shift(1)).abs().sum(axis=1)
    costs = turnover * (cost_bps / 1e4)
    net = gross - costs

    return {"gross": gross, "net": net, "turnover": turnover, **_metrics(gross, net, turnover)}


def _sharpe(x: pd.Series) -> float:
    x = x.dropna()
    s = x.std(ddof=0)
    return float(x.mean() / s * np.sqrt(TRADING_DAYS)) if s > 0 and len(x) else 0.0


def _metrics(gross: pd.Series, net: pd.Series, turnover: pd.Series) -> dict:
    net0 = net.fillna(0.0)
    equity = (1.0 + net0).cumprod()
    max_dd = float((equity / equity.cummax() - 1.0).min()) if len(equity) else 0.0
    ann = float(equity.iloc[-1] ** (TRADING_DAYS / max(len(net0), 1)) - 1.0) if len(net0) else 0.0
    return {
        "gross_sharpe": _sharpe(gross),
        "net_sharpe": _sharpe(net),
        "ann_return": ann,
        "max_drawdown": max_dd,
        "avg_turnover": float(turnover.mean()) if len(turnover) else 0.0,
        "days": int(net.notna().sum()),
    }
