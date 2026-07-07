"""FRED macro / credit overlay — a forward-looking risk-off timing signal.

The cross-sectional study found a price-only book is regime-dependent: it does fine in calm
markets and gives it back in risk-off episodes (2022). A directional, long-only equity book is
even more exposed — it is basically market beta. This module builds an EXOGENOUS, macro-based
risk-appetite signal from credit spreads and volatility (the two cleanest, highest-frequency
risk-off barometers) and uses it to CONDITION equity exposure: cut the book when credit and vol
say risk-off, run it when they say risk-on. It is a *timing overlay*, not new cross-sectional
alpha — it cannot change a signal's sign, only re-time when the exposure is on.

Data (FRED, keyless public CSV — no API key needed):
  * BAMLH0A0HYM2 — ICE BofA US High-Yield OAS (the credit-risk premium; the first thing to blow
    out in a risk-off, and it leads equity drawdowns).
  * BAMLC0A0CM  — ICE BofA US Investment-Grade OAS (reported alongside, for context).
  * VIXCLS      — CBOE VIX (implied equity vol; the market's own fear gauge).

Everything is CAUSAL: the risk-appetite score applied to day-t returns is built only from data
through t-1 (rolling/trailing statistics, then an explicit shift(1)). No look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import requests

from . import store

MACRO_DIR = store.DATA_DIR / "macro"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

# The three series this overlay is built on.
HY_OAS = "BAMLH0A0HYM2"   # High-Yield option-adjusted spread
IG_OAS = "BAMLC0A0CM"     # Investment-Grade option-adjusted spread
VIX = "VIXCLS"            # CBOE VIX


def fred_series(series_id: str, *, refresh: bool = False) -> pd.Series:
    """Fetch one FRED series as a date-indexed float Series, caching the raw CSV locally.

    FRED's public graph endpoint returns a two-column CSV (observation_date, {series_id}) with no
    API key required. Missing observations are encoded as "." → NaN. The CSV is cached under
    research/data/macro/ so repeated studies read locally (pass refresh=True to re-download)."""
    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    path = MACRO_DIR / f"{series_id}.csv"
    if refresh or not path.exists():
        resp = requests.get(FRED_CSV.format(series_id=series_id), timeout=30)
        resp.raise_for_status()
        path.write_bytes(resp.content)
    df = pd.read_csv(path, na_values=["."], parse_dates=["observation_date"])
    s = df.set_index("observation_date")[series_id].astype(float)
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def fetch_macro_frame(*, refresh: bool = False) -> pd.DataFrame:
    """The three raw daily series aligned on their business-day union (hy, ig, vix).

    Series are forward-filled across the small calendar gaps between them (a FRED holiday in one
    series shouldn't null the others); this only carries the LAST KNOWN value forward, never a
    future one, so it stays causal."""
    hy = fred_series(HY_OAS, refresh=refresh)
    ig = fred_series(IG_OAS, refresh=refresh)
    vix = fred_series(VIX, refresh=refresh)
    frame = pd.DataFrame({"hy": hy, "ig": ig, "vix": vix}).sort_index()
    return frame.ffill()


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def risk_appetite_from_frame(frame: pd.DataFrame, *, level_window: int = 252,
                             mom_window: int = 21, min_periods: int = 63) -> pd.DataFrame:
    """Continuous risk-appetite score in [0,1] (1 = full risk-on) from a raw hy/vix frame.

    Pure and testable — takes the raw daily frame (columns 'hy', 'vix'; 'ig' ignored here) and
    returns a frame with the blended `score` and its three components. NOT yet shifted or aligned
    to a trading calendar — that (the causal step) happens in `risk_off_state`.

    Construction — three risk-off "pressures", each a trailing z-score (so it is comparable across
    regimes and uses only past data), squashed to a [0,1] risk-ON sub-score via 1/(1+e^{+pressure}):

      * HY momentum   — the `mom_window`-day change in HY OAS, standardized by the trailing std of
        that change. Rising spreads (positive change) ⇒ risk-off ⇒ low score. This is the
        forward-looking piece: credit *turning* leads equity drawdowns.
      * HY level      — HY OAS vs its trailing `level_window`-day median, standardized by trailing
        std. Wide spreads ⇒ risk-off.
      * VIX level     — VIX vs its trailing median, standardized. Elevated implied vol ⇒ risk-off.

    The three risk-on sub-scores are averaged. Warm-up days (before `min_periods` of history) get a
    neutral 1.0 (full exposure) so the overlay never cuts the book on a signal it cannot yet form."""
    hy = frame["hy"].astype(float)
    vix = frame["vix"].astype(float)

    def _z(x: pd.Series) -> pd.Series:
        med = x.rolling(level_window, min_periods=min_periods).median()
        sd = x.rolling(level_window, min_periods=min_periods).std(ddof=0)
        return (x - med) / sd.where(sd > 0)

    # HY momentum pressure: standardized change in the spread over mom_window.
    hy_chg = hy.diff(mom_window)
    chg_sd = hy_chg.rolling(level_window, min_periods=min_periods).std(ddof=0)
    p_mom = hy_chg / chg_sd.where(chg_sd > 0)
    p_level = _z(hy)      # HY level pressure
    p_vix = _z(vix)       # VIX level pressure

    # Each pressure > 0 is risk-off, so map to a risk-ON sub-score with sigmoid(-pressure).
    s_mom = _sigmoid(-p_mom)
    s_level = _sigmoid(-p_level)
    s_vix = _sigmoid(-p_vix)
    score = pd.concat([s_mom, s_level, s_vix], axis=1).mean(axis=1).fillna(1.0).clip(0.0, 1.0)

    return pd.DataFrame({"score": score, "hy_mom": s_mom, "hy_level": s_level, "vix_level": s_vix})


def _to_naive_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Normalize a (possibly tz-aware) DatetimeIndex to naive, midnight-stamped dates for alignment
    against FRED's naive daily calendar."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def risk_off_state(index: pd.DatetimeIndex, *, frame: pd.DataFrame | None = None,
                   refresh: bool = False, **kwargs) -> dict:
    """Causal risk-appetite score aligned to a trading calendar `index` (the equity panel dates).

    Returns a dict:
      * 'score' — risk-appetite in [0,1] (1 = full risk-on), aligned to `index` and SHIFTED BY ONE
        trading day, so the allocation for day t uses only macro data observed through t-1.
      * 'hy', 'ig', 'vix' — the raw FRED levels aligned to `index` (for reporting), also shifted.
      * 'raw_score' — the un-shifted score on `index` (diagnostic; do not trade on it).

    `frame` (columns hy/ig/vix) may be injected to bypass the network (used by tests)."""
    if frame is None:
        frame = fetch_macro_frame(refresh=refresh)

    comp = risk_appetite_from_frame(frame, **kwargs)

    # Align the daily FRED calendar onto the trading calendar: build everything on FRED's own dense
    # daily history (so trailing windows are correct), then forward-fill onto the panel dates and
    # shift one day. ffill carries the last KNOWN observation, never a future one.
    target = _to_naive_dates(index)

    def _align(series: pd.Series) -> pd.Series:
        s = series.copy()
        s.index = _to_naive_dates(series.index)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        aligned = s.reindex(s.index.union(target)).ffill().reindex(target)
        aligned.index = index                      # restore the caller's original index labels
        return aligned

    raw_score = _align(comp["score"])
    out = {
        "score": raw_score.shift(1),               # causal: day-t exposure uses data through t-1
        "raw_score": raw_score,
        "hy": _align(frame["hy"]).shift(1),
        "ig": _align(frame["ig"]).shift(1),
        "vix": _align(frame["vix"]).shift(1),
    }
    return out
