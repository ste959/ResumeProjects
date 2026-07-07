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


def _market_return(rets: pd.DataFrame) -> pd.Series:
    """Equal-weight universe return each day — our market proxy (the free feed has no index)."""
    return rets.mean(axis=1, skipna=True)


def _rolling_beta(rets: pd.DataFrame, mkt: pd.Series, window: int = 126) -> pd.DataFrame:
    """Rolling market beta per name: cov(r_i, mkt) / var(mkt). Slow-moving → low turnover."""
    mkt_var = mkt.rolling(window).var()
    return pd.DataFrame({col: rets[col].rolling(window).cov(mkt) / mkt_var for col in rets.columns})


def _idio_vol(rets: pd.DataFrame, mkt: pd.Series, window: int = 126) -> pd.DataFrame:
    """Rolling idiosyncratic volatility per name: the vol left after removing the market
    component. idio_var = var(r_i) − cov(r_i, mkt)² / var(mkt) (residual variance from a single
    CAPM regression). Distinct from raw total vol — that's what makes it a real anomaly."""
    mkt_var = mkt.rolling(window).var()
    out = {}
    for col in rets.columns:
        cov = rets[col].rolling(window).cov(mkt)
        var_i = rets[col].rolling(window).var()
        out[col] = np.sqrt((var_i - cov ** 2 / mkt_var).clip(lower=0))
    return pd.DataFrame(out)


def signals(px: pd.DataFrame, rets: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Cross-sectional signals, each a dates × symbols score (higher = long).

    All are price/volume-only — the free IEX feed has no fundamentals, so true value/quality/
    profitability factors are honestly off the table. These are technical/risk factors chosen to
    DIVERSIFY momentum (the best raw performer, though NOT statistically significant at this
    sample size — see the t-stat/CI reporting in run_crosssec.py), not just pile on more trend."""
    logpx = np.log(px)
    mom = logpx.diff(252) - logpx.diff(21)
    mkt = _market_return(rets)
    beta = _rolling_beta(rets, mkt)
    idio = _idio_vol(rets, mkt)
    return {
        # 12–1 month momentum: last ~12m return skipping the most recent month.
        "momentum": mom,
        # short-term reversal: last week's losers tend to bounce → negate the 5-day return.
        "reversal": -rets.rolling(5).sum(),
        # low-volatility: prefer calmer names → negate trailing total vol.
        "low_vol": -rets.rolling(21).std(),
        # betting-against-beta: long low-β names, short high-β (a risk bet, not a trend bet).
        "bab": -beta,
        # idiosyncratic-vol anomaly: long low residual-vol names (market component removed).
        "idio_vol": -idio,
        # risk-adjusted momentum: scale 12–1 momentum by idio-vol — a cleaner momentum.
        "risk_adj_mom": mom / idio.replace(0, np.nan),
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
    held = weights.shift(1)
    gross = (held * rets).sum(axis=1, skipna=True)
    turnover = (weights - weights.shift(1)).abs().sum(axis=1)
    costs = turnover * (cost_bps / 1e4)
    net = gross - costs

    # Active period only: during a signal's warm-up (e.g. 252-day momentum) every weight is 0,
    # so `sum(skipna=True)` yields a stream of flat 0.0 returns — dead capital, not a real flat
    # position. Counting those days would understate the Sharpe and skew the annualization
    # exponent. Mask everything before the first day the portfolio actually holds risk, so all
    # metrics reflect the active window. (No look-ahead: this only trims leading dead days.)
    active = held.abs().sum(axis=1) > 0
    if active.any():
        first = active.idxmax()
        pre = gross.index < first
        gross = gross.mask(pre)
        net = net.mask(pre)
        turnover = turnover.mask(pre)

    return {"gross": gross, "net": net, "turnover": turnover, **_metrics(gross, net, turnover)}


def _sharpe(x: pd.Series) -> float:
    x = x.dropna()
    s = x.std(ddof=0)
    return float(x.mean() / s * np.sqrt(TRADING_DAYS)) if s > 0 and len(x) else 0.0


def _metrics(gross: pd.Series, net: pd.Series, turnover: pd.Series) -> dict:
    # Only the active (non-warm-up) days count: NaN days are dropped so the equity curve, the
    # annualization exponent and the day count all reflect the period capital was actually at work.
    net_active = net.dropna()
    n = len(net_active)
    equity = (1.0 + net_active).cumprod()
    max_dd = float((equity / equity.cummax() - 1.0).min()) if n else 0.0
    ann = float(equity.iloc[-1] ** (TRADING_DAYS / max(n, 1)) - 1.0) if n else 0.0
    return {
        "gross_sharpe": _sharpe(gross),
        "net_sharpe": _sharpe(net),
        "ann_return": ann,
        "max_drawdown": max_dd,
        "avg_turnover": float(turnover.mean()) if len(turnover.dropna()) else 0.0,
        "days": n,
    }
