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


def _loo_market(rets: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-out market return per name (dates × symbols): each column is the equal-weight
    universe return with that name EXCLUDED. Regressing a stock on a benchmark that contains
    ~1/N of itself biases its beta up and understates its idiosyncratic vol; leaving it out fixes
    that. Where a name is missing that day it is already out of both the sum and the count."""
    n = rets.count(axis=1)
    total = rets.sum(axis=1)
    out = {}
    for col in rets.columns:
        denom = (n - rets[col].notna().astype(int)).replace(0, np.nan)
        out[col] = (total - rets[col].fillna(0.0)) / denom
    return pd.DataFrame(out)


def _col_market(mkt, col: str) -> pd.Series:
    """The benchmark series for one name: a per-name leave-one-out frame column, or a shared
    market Series (used by the unit tests, which pass a single known market)."""
    return mkt[col] if isinstance(mkt, pd.DataFrame) else mkt


def _rolling_beta(rets: pd.DataFrame, mkt, window: int = 126) -> pd.DataFrame:
    """Rolling market beta per name: cov(r_i, mkt_i) / var(mkt_i). Slow-moving → low turnover.
    `mkt` is a per-name leave-one-out frame (or a shared Series in tests)."""
    out = {}
    for col in rets.columns:
        m = _col_market(mkt, col)
        out[col] = rets[col].rolling(window).cov(m) / m.rolling(window).var()
    return pd.DataFrame(out)


def _idio_vol(rets: pd.DataFrame, mkt, window: int = 126) -> pd.DataFrame:
    """Rolling idiosyncratic volatility per name: the vol left after removing the market
    component. idio_var = var(r_i) − cov(r_i, mkt_i)² / var(mkt_i) (residual variance from a single
    CAPM regression on its leave-one-out benchmark). Distinct from raw total vol — that's the anomaly."""
    out = {}
    for col in rets.columns:
        m = _col_market(mkt, col)
        cov = rets[col].rolling(window).cov(m)
        var_i = rets[col].rolling(window).var()
        out[col] = np.sqrt((var_i - cov ** 2 / m.rolling(window).var()).clip(lower=0))
    return pd.DataFrame(out)


def _sector_relative(frame: pd.DataFrame, sectors: dict) -> pd.DataFrame:
    """Subtract each day's sector mean from every name — the intra-industry (sector-neutral) part of
    a signal. Built neutral BY CONSTRUCTION, so its edge cannot be uncompensated sector exposure
    (the thing that turned out to explain most of raw momentum's apparent edge)."""
    sec = pd.Series(sectors).reindex(frame.columns)
    sector_mean = frame.T.groupby(sec.to_numpy()).transform("mean").T
    return frame - sector_mean


def signals(px: pd.DataFrame, rets: pd.DataFrame, bars: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Cross-sectional signals, each a dates × symbols score (higher = long).

    Price/volume-only — the free IEX feed has no fundamentals. The first six are the classic
    close-only factors; the last five are new, motivated by the results (raw edge was mostly
    sector/factor exposure; the OHLC/vwap fields were unused) and by tapping open/high/low/vwap.
    Adding them grows the multiple-testing family to 11, so the Deflated-Sharpe bar deflates
    harder — the value is a disciplined test, not fishing (see run_crosssec.py)."""
    logpx = np.log(px)
    mom = logpx.diff(252) - logpx.diff(21)
    loo = _loo_market(rets)          # each name's benchmark excludes itself (no self-inclusion bias)
    beta = _rolling_beta(rets, loo)
    idio = _idio_vol(rets, loo)

    # New signals draw on the previously-unused OHLC/vwap/volume/trades fields (injectable for testing).
    if bars is None:
        bars = ad.load_bars()

    def _panel(field):
        return ad.close_panel(bars, field).reindex(index=px.index, columns=px.columns)

    open_p, vwap_p = _panel("open"), _panel("vwap")
    volume, trades = _panel("volume"), _panel("trades")
    overnight = np.log(open_p) - np.log(px.shift(1))           # open_t vs prior close: the overnight leg
    resid_ret = _sector_relative(rets, SECTORS)               # daily return net of its sector

    # Order-flow proxies — daily-bar shadows of the microstructure order-flow that drives real
    # microstructure alpha (Cont et al. OFI). A day that closes ABOVE its VWAP had net buying
    # pressure, so sign each day's volume by (close − vwap) and net it over a short window.
    signed_vol = volume * np.sign(px - vwap_p)
    flow_pressure = signed_vol.rolling(5).sum() / volume.rolling(5).sum().replace(0, np.nan)
    # Average trade size (volume / #trades) is an institutional-participation proxy; a rising one
    # signals accumulation. The raw ratio is noisy day-to-day, so SMOOTH it (21d mean) and take the
    # slow trend vs its 63d mean — a low-turnover accumulation signal, not a tick-noise machine.
    avg_trade_size = (volume / trades.replace(0, np.nan)).rolling(21).mean()
    participation_trend = np.log(avg_trade_size) - np.log(avg_trade_size.rolling(63).mean())

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
        # ── new ──────────────────────────────────────────────────────────────────────────────
        # ① sector-relative (intra-industry) momentum — the name-specific part, sector-neutral by
        #    construction (motivated by neutralization killing most of raw momentum's edge).
        "sector_rel_mom": _sector_relative(mom, SECTORS),
        # ② overnight-return factor (Lou–Polk–Skouras): trailing mean overnight leg; the overnight
        #    and intraday premia differ — a genuinely orthogonal axis from the unused `open`.
        "overnight": overnight.rolling(21).mean(),
        # ③ sector-relative short-term reversal — reversal on the residual return; lower-turnover,
        #    tests whether removing the sector component salvages the (significant) reversal effect.
        "sector_rel_rev": -resid_ret.rolling(5).sum(),
        # ④ close-vs-VWAP pressure — persistent closing above the day's volume-weighted average as
        #    a buying-pressure signal (from the unused `vwap`), smoothed to keep turnover down.
        "vwap_pressure": ((px - vwap_p) / vwap_p).rolling(5).mean(),
        # ⑤ MAX / lottery-demand (Bali–Cakici–Whitelaw): short names with extreme recent up-days;
        #    a skewness/attention effect distinct from the second-moment vol signals.
        "max_lottery": -rets.rolling(21).apply(lambda x: np.mean(np.sort(x)[-5:]), raw=True),
        # ── order flow (the last unused fields: volume, trades) ────────────────────────────────
        # ⑥ flow pressure — net signed volume (buy if close>vwap) over a week; the daily-bar OFI
        #    proxy, the closest thing to real order flow in daily data. Higher = persistent buying.
        "flow_pressure": flow_pressure,
        # ⑦ participation trend — smoothed average trade size (volume/#trades) vs its own slower
        #    mean; rising institutional participation as a low-turnover accumulation signal.
        "trade_size_trend": participation_trend,
    }


def _xs_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score each day (demean and scale across symbols, excluding NaNs)."""
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0)


# GICS sector map (single source of truth in alpaca_data, alongside the universe it classifies) —
# used to build a genuinely sector-neutral book, not merely dollar-neutral.
SECTORS = ad.SECTORS


def dollar_adv_panel(window: int = 20) -> pd.DataFrame:
    """Trailing average dollar volume (close × share volume) per name — an ADV proxy for the market-
    impact model. Shifted so day-t sizing uses only volume through t−1. NB: free IEX volume is a
    fraction of consolidated volume, so this OVERSTATES impact (a conservative bias)."""
    bars = ad.load_bars()
    dv = (ad.close_panel(bars, "close") * ad.close_panel(bars, "volume")).sort_index()
    return dv.rolling(window, min_periods=5).mean().shift(1)


def neutralize(weights: pd.DataFrame, beta: pd.DataFrame, sectors: dict) -> pd.DataFrame:
    """Residualize each day's weights against market beta AND sector dummies, then renormalize to
    unit gross. The residual is orthogonal to beta and to every sector, so the book is beta- and
    sector-neutral — not merely dollar-neutral. This is the difference between a toy long/short and
    an investable factor-neutral one."""
    sec = pd.Series(sectors).reindex(weights.columns)
    dummies = pd.get_dummies(sec, dtype=float).to_numpy()          # (M symbols × K sectors)
    out = pd.DataFrame(0.0, index=weights.index, columns=weights.columns)
    W, B = weights.to_numpy(), beta.reindex_like(weights).to_numpy()
    for i in range(len(weights)):
        w = W[i]
        cols = np.where(np.isfinite(w) & (w != 0))[0]
        if len(cols) < 4:
            continue
        wv = w[cols]
        b = B[i, cols]
        b = np.where(np.isfinite(b), b, np.nanmean(b) if np.isfinite(b).any() else 0.0)
        X = np.column_stack([b - b.mean(), dummies[cols]])         # sectors span the constant
        X = X[:, X.std(axis=0) > 0]                                # drop absent sectors
        coef, *_ = np.linalg.lstsq(X, wv, rcond=None)
        out.iloc[i, cols] = wv - X @ coef                          # residual: β- and sector-neutral
    g = out.abs().sum(axis=1).replace(0, np.nan)
    return out.div(g, axis=0).fillna(0.0)


def raw_weights(signal: pd.DataFrame) -> pd.DataFrame:
    """Dollar-neutral, unit-gross weights from a signal (the toy book)."""
    w = _xs_zscore(signal)
    g = w.abs().sum(axis=1).replace(0, np.nan)
    return w.div(g, axis=0).fillna(0.0)


def neutralized_weights(signal: pd.DataFrame, rets: pd.DataFrame) -> pd.DataFrame:
    """Beta- and sector-neutral weights for a signal (the investable book)."""
    return neutralize(raw_weights(signal), _rolling_beta(rets, _loo_market(rets)), SECTORS)


def book_beta(weights: pd.DataFrame, rets: pd.DataFrame) -> pd.Series:
    """The portfolio's net market beta each day = Σ_i w_i · β_i (held one day, no look-ahead)."""
    beta = _rolling_beta(rets, _loo_market(rets)).reindex_like(weights)
    return (weights.shift(1) * beta).sum(axis=1, skipna=True)


def backtest(signal: pd.DataFrame, rets: pd.DataFrame, cost_bps: float = 5.0, *,
             weights: pd.DataFrame | None = None, impact_coef: float = 0.0,
             borrow_bps: float = 0.0, dollar_vol: pd.DataFrame | None = None,
             gross_capital: float = 1e7) -> dict:
    """Backtest a cross-sectional signal as a dollar-neutral, unit-gross portfolio.

    Costs: a flat `cost_bps` per unit turnover (half-spread + fee); optionally a square-root
    **market-impact** term (`impact_coef`·√participation, participation = trade$/ADV$) and a
    **short-borrow/financing** charge (`borrow_bps` annual on the short leg). Pass pre-built
    `weights` (e.g. beta/sector-neutralized) to bypass the raw z-score construction."""
    if weights is None:
        weights = _xs_zscore(signal)
        gross_exposure = weights.abs().sum(axis=1).replace(0, np.nan)
        weights = weights.div(gross_exposure, axis=0).fillna(0.0)  # dollar-neutral, unit gross

    # Held one day: weights decided at t earn the t→t+1 return (no look-ahead).
    held = weights.shift(1)
    gross = (held * rets).sum(axis=1, skipna=True)
    dtrade = (weights - weights.shift(1)).abs()
    turnover = dtrade.sum(axis=1)
    costs = turnover * (cost_bps / 1e4)

    # Market impact (√-law) and short borrow — off by default (impact_coef=0, borrow_bps=0).
    if impact_coef > 0 and dollar_vol is not None:
        adv = dollar_vol.reindex_like(weights)
        participation = (dtrade * gross_capital / adv).clip(lower=0).fillna(0.0)
        costs = costs + (impact_coef * np.sqrt(participation) * dtrade).sum(axis=1)
    if borrow_bps > 0:
        short_gross = held.clip(upper=0).abs().sum(axis=1)         # ~0.5 of unit gross
        costs = costs + short_gross * (borrow_bps / 1e4) / TRADING_DAYS
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
