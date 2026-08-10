"""Options-expiration ("OPEX") structural effects — the price footprint of the dealer-gamma cycle.

Why this is *structural* (and so more durable than a statistical pattern): options dealers hedge
**mechanically**. When they're net long gamma they sell strength / buy weakness — damping vol and
"pinning" the underlying toward big-open-interest strikes into monthly expiry; when that gamma **rolls
off** the third Friday, the damping is removed and the week *after* expiration has historically drifted
weak. Nobody arbitrages this away because the hedging isn't a bet — it's a mandate.

The clean, fully-backtestable signal here is the **OPEX calendar phase** (it needs only daily prices, which
we have). Computing true Gamma Exposure (GEX) needs option **open interest by strike** — which the free
Alpaca feed does not provide — so `gamma_by_strike` below is the *methodology* (Black–Scholes gamma × a
volume proxy), clearly labeled, not a backtest input. Pure NumPy/pandas; the strategy plugs into the engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .engine import Strategy

TRADING_DAYS = 252


# ── OPEX calendar ─────────────────────────────────────────────────────────────────────────────────
def _naive(index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    return idx.tz_localize(None) if idx.tz is not None else idx


def monthly_expiries(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """The monthly options-expiration dates (3rd Friday of each month) spanning the index (tz-naive)."""
    idx = _naive(index)
    out = []
    for period in pd.period_range(idx.min(), idx.max(), freq="M"):
        first = period.to_timestamp()
        fridays = pd.date_range(first, first + pd.offsets.MonthEnd(0), freq="W-FRI")
        if len(fridays) >= 3:
            out.append(fridays[2])                       # the 3rd Friday
    return pd.DatetimeIndex(out)


def opex_phase(index: pd.DatetimeIndex) -> pd.Series:
    """Classify each trading day by its position in the OPEX cycle: `opex_week` (the 5 sessions up to and
    including expiry), `post_opex` (the 5 sessions after), else `rest`. Trading-day distances, so holidays
    don't shift the windows. Handles tz-aware indexes (real feeds) transparently."""
    orig = pd.DatetimeIndex(index)
    idx = _naive(orig)
    phase = np.full(len(idx), "rest", dtype=object)
    exp_positions = [int(idx.searchsorted(e)) for e in monthly_expiries(idx)]
    exp_positions = [ep for ep in exp_positions if ep < len(idx)]
    for ep in exp_positions:
        phase[max(0, ep - 4):ep + 1] = "opex_week"       # 5 sessions up to & including expiry
    for ep in exp_positions:
        phase[ep + 1:ep + 6] = "post_opex"               # 5 sessions after
    return pd.Series(phase, index=orig)


def phase_return_study(prices: pd.Series, ppy: int = TRADING_DAYS) -> pd.DataFrame:
    """Mean daily return, annualized drift, and a t-stat for each OPEX phase — is the calendar effect real?"""
    rets = prices.pct_change().dropna()
    phase = opex_phase(rets.index)
    rows = []
    for name in ("opex_week", "post_opex", "rest"):
        r = rets[phase == name].to_numpy()
        if len(r) < 10:
            continue
        t = float(r.mean() / (r.std() / np.sqrt(len(r)))) if r.std() > 0 else 0.0
        rows.append({"phase": name, "n_days": len(r), "mean_daily": r.mean(),
                     "ann_drift": r.mean() * ppy, "t_stat": t})
    return pd.DataFrame(rows).set_index("phase")


class OpexTiming(Strategy):
    """Long the underlying except during the phase(s) flagged weak by the gamma-roll-off structure —
    default: flat in `post_opex` (support removed once dealer gamma expires). A single-name timing overlay
    that isolates the calendar effect; benchmark it against always-long."""
    name = "opex-timing"
    warmup = 30

    def __init__(self, symbol: str = "SPY", weights: dict | None = None):
        self._symbol = symbol
        self._w = weights or {"opex_week": 1.0, "rest": 1.0, "post_opex": 0.0}
        self._phase = None

    def symbols(self) -> list[str]:
        return [self._symbol]

    def prepare(self, prices: pd.DataFrame) -> None:
        self._phase = opex_phase(prices.index)

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        ph = self._phase.iloc[t - 1]                     # phase known as of the prior close
        return np.array([self._w.get(ph, 1.0)])


# ── Gamma methodology (OI-limited; disclosed) ─────────────────────────────────────────────────────
def bs_gamma(S: float, K: float, T: float, sigma: float, r: float = 0.04) -> float:
    """Black–Scholes gamma — the second derivative of option value w.r.t. spot (identical for calls/puts)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))


def gamma_by_strike(chain: pd.DataFrame, spot: float, oi_col: str = "volume") -> pd.DataFrame:
    """Dealer-gamma concentration by strike: Σ γ · size · spot² · 100, with calls +/puts − (the usual
    dealer-short-puts convention). **Methodology only** — true GEX needs open interest by strike, which the
    free feed lacks, so `oi_col` defaults to daily *volume* as a rough activity proxy. Use to *illustrate*
    where hedging pressure concentrates and the zero-gamma flip level, not as a backtest input."""
    df = chain.dropna(subset=["strike", "iv", "expiry"]).copy()
    if df.empty:
        return pd.DataFrame(columns=["strike", "gamma_exposure"])
    T = (pd.to_datetime(df["expiry"]) - pd.Timestamp.today()).dt.days.clip(lower=1) / 365.0
    g = np.array([bs_gamma(spot, k, t, s) for k, t, s in zip(df["strike"], T, df["iv"])])
    size = df[oi_col].fillna(0.0).to_numpy()
    sign = np.where(df["right"].str.lower().str[0] == "c", 1.0, -1.0)   # dealer short puts → negative
    df["gamma_exposure"] = sign * g * size * spot ** 2 * 100.0
    return df.groupby("strike", as_index=False)["gamma_exposure"].sum().sort_values("strike")
