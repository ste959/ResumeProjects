"""Options-implied cross-sectional signals from Alpaca's option snapshots (indicative feed).

Equities cross-section (crosssec.py) reads what the STOCK did; this layer reads what the options
market is PRICING for the future — the implied-vol surface. Three classic option-implied signals,
each a per-name number that ranks the cross-section:

  * ATM implied vol — the level of expected volatility (|delta|≈0.5 contract).
  * 25-delta risk-reversal skew — IV(25Δ put) − IV(25Δ call). Positive = downside protection is
    bid up relative to upside calls, the standard "fear"/crash-premium gauge.
  * put/call volume ratio — a sentiment/flow proxy from the daily-bar volumes.

Paired with a realized-vol estimate from the cached bars, ATM IV − RV is the variance-risk-premium
proxy (how much more vol the option market charges than the stock has recently delivered).

IMPORTANT — this is POINT-IN-TIME. Alpaca option snapshots are LIVE (today's surface); there is no
free historical IV panel, so this module computes a *today* cross-section, not a backtest. See
run_options.py for the honest scoping of what a backtest would need (accumulated daily snapshots or
a per-contract historical-bars fetch — the latter is gated behind a signed OPRA agreement, which
this account lacks: /v1beta1/options/bars returns 403 "OPRA agreement is not signed").

Only READS from the shared modules (alpaca_data for credentials + universe); never mutates them.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import alpaca_data as ad
from . import store

SNAPSHOTS_URL = "https://data.alpaca.markets/v1beta1/options/snapshots/{underlying}"
BARS_URL = "https://data.alpaca.markets/v1beta1/options/bars"
OPTIONS_DIR = store.DATA_DIR / "options"

UNIVERSE = ad.UNIVERSE


# ── OCC symbol parsing ────────────────────────────────────────────────────────────────────────
def parse_occ(occ: str) -> dict:
    """Parse an OCC option symbol into its fields, decoding from the RIGHT (robust to multi-char
    roots). Layout: ROOT + YYMMDD + {C,P} + strike*1000 zero-padded to 8 digits.

        AAPL260706C00210000 → underlying AAPL, expiry 2026-07-06, right C, strike 210.0
        (strike = last 8 digits / 1000 = 00210000 / 1000 = 210.0)
    """
    occ = occ.strip().upper()
    strike = int(occ[-8:]) / 1000.0
    right = occ[-9]
    ymd = occ[-15:-9]
    underlying = occ[:-15]
    if right not in ("C", "P") or not ymd.isdigit() or not underlying.isalpha():
        raise ValueError(f"not a valid OCC symbol: {occ}")
    expiry = dt.date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    return {"underlying": underlying, "expiry": expiry, "right": right, "strike": strike}


# ── network ───────────────────────────────────────────────────────────────────────────────────
def _headers() -> dict:
    kid, sec = ad._credentials()
    return {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}


def option_snapshots(underlying: str, *, max_dte: int = 45, max_pages: int = 4,
                     feed: str = "indicative", asof: dt.date | None = None) -> pd.DataFrame:
    """Fetch the option-chain snapshots for one underlying and parse each contract into a row.

    Filters server-side to expiries in [today, today+max_dte] (the nearest weeklies/monthlies) so a
    123-name sweep stays light, then paginates (capped at max_pages). Contracts without a live
    quote/greeks come back with NaN iv/delta — kept, not dropped, so counts are honest.

    Returns columns: underlying, occ, expiry, right, strike, iv, delta, bid, ask, mid, volume.
    Any error (auth, network, empty chain) → empty DataFrame (the sweep skips the name).
    """
    cols = ["underlying", "occ", "expiry", "right", "strike", "iv", "delta",
            "bid", "ask", "mid", "volume"]
    today = asof or dt.date.today()
    params = {
        "feed": feed,
        "limit": 1000,
        "expiration_date_gte": today.isoformat(),
        "expiration_date_lte": (today + dt.timedelta(days=max_dte)).isoformat(),
    }
    rows: list[dict] = []
    token = None
    try:
        for _ in range(max_pages):
            p = dict(params)
            if token:
                p["page_token"] = token
            resp = requests.get(SNAPSHOTS_URL.format(underlying=underlying),
                                headers=_headers(), params=p, timeout=30)
            if resp.status_code == 429:      # rate limited — back off and retry this page
                time.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            for occ, snap in (data.get("snapshots") or {}).items():
                try:
                    f = parse_occ(occ)
                except ValueError:
                    continue
                q = snap.get("latestQuote") or {}
                bid, ask = q.get("bp"), q.get("ap")
                # Null check, not truthiness: a legitimate 0.0 bid (deep-OTM, no resting bid) is falsy,
                # so `if bid and ask` would wrongly drop a real quote. Test for presence explicitly.
                mid = ((bid + ask) / 2.0) if (bid is not None and ask is not None) else None
                greeks = snap.get("greeks") or {}
                daily = snap.get("dailyBar") or {}
                rows.append({
                    "underlying": f["underlying"], "occ": occ, "expiry": f["expiry"],
                    "right": f["right"], "strike": f["strike"],
                    "iv": snap.get("impliedVolatility"), "delta": greeks.get("delta"),
                    "bid": bid, "ask": ask, "mid": mid, "volume": daily.get("v"),
                })
            token = data.get("next_page_token")
            if not token:
                break
    except Exception:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


# ── signal computation (network-free core; unit-tested) ─────────────────────────────────────────
def _interp_at_delta(deltas: np.ndarray, ivs: np.ndarray, target: float) -> float:
    """Interpolate IV to a target delta along one side of the smile. np.interp needs ascending x, so
    sort by delta; outside the observed range it clamps to the nearest point (documented behaviour —
    we take the closest OTM contract rather than extrapolate a fabricated wing)."""
    m = np.isfinite(deltas) & np.isfinite(ivs)
    deltas, ivs = deltas[m], ivs[m]
    if len(deltas) == 0:
        return float("nan")
    order = np.argsort(deltas)
    return float(np.interp(target, deltas[order], ivs[order]))


def compute_signals(rows: pd.DataFrame, *, min_contracts: int = 6, min_dte: int = 5,
                    asof: dt.date | None = None) -> dict:
    """Compute the option-implied signals for one name from its snapshot rows (no network).

    Picks the NEAREST expiry that is at least `min_dte` days out (skipping 0DTE, whose greeks are
    degenerate) and has ≥`min_contracts` contracts with valid iv+delta on both put and call sides,
    then reads the smile:
        atm_iv     = mean IV interpolated to |delta|≈0.5 on each side
        skew_25d   = IV(25Δ put) − IV(25Δ call)   (positive = downside fear bid up)
        pcr_volume = Σ put daily volume / Σ call daily volume, over the whole fetched chain
    Returns NaNs (and expiry=None) when no expiry qualifies.
    """
    empty = {"atm_iv": float("nan"), "skew_25d": float("nan"), "iv_25p": float("nan"),
             "iv_25c": float("nan"), "pcr_volume": float("nan"), "expiry": None,
             "dte": float("nan"), "n_contracts": 0}
    if rows is None or rows.empty:
        return empty
    today = asof or dt.date.today()
    valid = rows[np.isfinite(rows["iv"]) & np.isfinite(rows["delta"])].copy()
    if valid.empty:
        return empty

    # Pick the target expiry: nearest with enough valid contracts on BOTH sides, dte ≥ min_dte.
    target_exp, target_dte = None, None
    for exp in sorted(valid["expiry"].unique()):
        dte = (exp - today).days
        if dte < min_dte:
            continue
        sub = valid[valid["expiry"] == exp]
        n_c = int((sub["right"] == "C").sum())
        n_p = int((sub["right"] == "P").sum())
        if n_c >= 2 and n_p >= 2 and (n_c + n_p) >= min_contracts:
            target_exp, target_dte = exp, dte
            break
    if target_exp is None:
        return empty

    sub = valid[valid["expiry"] == target_exp]
    calls = sub[sub["right"] == "C"]
    puts = sub[sub["right"] == "P"]
    cd, cv = calls["delta"].to_numpy(), calls["iv"].to_numpy()
    pd_, pv = puts["delta"].to_numpy(), puts["iv"].to_numpy()

    atm_call = _interp_at_delta(cd, cv, 0.5)
    atm_put = _interp_at_delta(pd_, pv, -0.5)
    atm_iv = float(np.nanmean([atm_call, atm_put]))
    iv_25c = _interp_at_delta(cd, cv, 0.25)
    iv_25p = _interp_at_delta(pd_, pv, -0.25)
    skew_25d = iv_25p - iv_25c

    # Put/call volume ratio over the whole fetched chain (a broader sentiment read than one expiry).
    put_vol = rows.loc[rows["right"] == "P", "volume"].fillna(0).sum()
    call_vol = rows.loc[rows["right"] == "C", "volume"].fillna(0).sum()
    pcr = float(put_vol / call_vol) if call_vol > 0 else float("nan")

    return {"atm_iv": atm_iv, "skew_25d": skew_25d, "iv_25p": iv_25p, "iv_25c": iv_25c,
            "pcr_volume": pcr, "expiry": target_exp, "dte": float(target_dte),
            "n_contracts": int(len(sub))}


def iv_skew(underlying: str, **kw) -> dict:
    """Fetch one name's chain and compute its option-implied signals (see compute_signals)."""
    rows = option_snapshots(underlying)
    out = compute_signals(rows, **kw)
    out["symbol"] = underlying
    return out


# ── cross-section ───────────────────────────────────────────────────────────────────────────────
def cross_section(universe=UNIVERSE, *, sleep: float = 0.15, cache: bool = True,
                  asof: dt.date | None = None) -> pd.DataFrame:
    """Build the POINT-IN-TIME option-implied cross-section over the universe and cache it.

    Loops the names (a short sleep between them for rate limits), fetching each chain and reducing it
    to one row {symbol, atm_iv, skew_25d, iv_25p, iv_25c, pcr_volume, expiry, dte, n_contracts}.
    Names whose chain is empty or has no qualifying expiry are dropped. Written to
    research/data/options/snapshot_{asof}.parquet (research/data is gitignored)."""
    asof = asof or dt.date.today()
    records = []
    for i, sym in enumerate(universe):
        rows = option_snapshots(sym, asof=asof)
        sig = compute_signals(rows, asof=asof)
        sig["symbol"] = sym
        if sig["n_contracts"] > 0 and np.isfinite(sig["atm_iv"]):
            records.append(sig)
        if sleep and i < len(universe) - 1:
            time.sleep(sleep)
    df = pd.DataFrame.from_records(records)
    if not df.empty:
        df = df[["symbol", "atm_iv", "skew_25d", "iv_25p", "iv_25c", "pcr_volume",
                 "expiry", "dte", "n_contracts"]].sort_values("symbol").reset_index(drop=True)
    if cache and not df.empty:
        store.write_parquet(df, OPTIONS_DIR / f"snapshot_{asof.isoformat()}.parquet")
    return df


# ── historical bars (the backtest data path — outlined, not a fabricated signal) ────────────────
def option_bars(occ: str, start: str, end: str, timeframe: str = "1Day") -> tuple[pd.DataFrame, str]:
    """Fetch historical daily bars for ONE option contract (its PRICE history, not IV).

    This is the raw material for a historical study, but it is GATED: /v1beta1/options/bars serves
    the OPRA feed only, so an account without a signed OPRA data agreement gets HTTP 403 ("OPRA
    agreement is not signed") — the indicative feed used for snapshots does NOT extend to bars, and
    the endpoint rejects a `feed` param. Where bars ARE available (OPRA signed, data starts
    ~2024-02), turning them into a historical IV panel still needs a Black–Scholes inversion per bar
    (underlying + strike + dte + rate → IV) plus identifying which contract was ATM/25Δ on each past
    date. Returns (bars_df, status) where status is "ok", "empty", or a short reason (e.g. the 403
    message) so callers can report the gating honestly instead of silently showing no data."""
    cols = ["ts", "open", "high", "low", "close", "volume"]
    try:
        rows = []
        token = None
        for _ in range(20):
            params = {"symbols": occ, "timeframe": timeframe, "start": start, "end": end,
                      "limit": 10000}
            if token:
                params["page_token"] = token
            resp = requests.get(BARS_URL, headers=_headers(), params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(2)
                continue
            if resp.status_code != 200:
                msg = (resp.json().get("message") if resp.headers.get("content-type", "")
                       .startswith("application/json") else resp.text) or f"HTTP {resp.status_code}"
                return pd.DataFrame(columns=cols), str(msg)[:120]
            data = resp.json()
            for bar in (data.get("bars") or {}).get(occ, []):
                rows.append({"ts": bar["t"], "open": bar["o"], "high": bar["h"],
                             "low": bar["l"], "close": bar["c"], "volume": bar["v"]})
            token = data.get("next_page_token")
            if not token:
                break
        df = pd.DataFrame(rows, columns=cols)
        if not df.empty:
            df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df, ("ok" if not df.empty else "empty")
    except Exception as e:
        return pd.DataFrame(columns=cols), f"error: {e}"[:120]


def atm_contract(underlying: str, asof: dt.date | None = None) -> str | None:
    """OCC symbol of the near-ATM call (delta closest to 0.5) in the nearest qualifying expiry —
    a convenience for the historical-bars illustration in run_options.py."""
    rows = option_snapshots(underlying, asof=asof)
    sig = compute_signals(rows, asof=asof)
    exp = sig.get("expiry")
    if exp is None or rows.empty:
        return None
    calls = rows[(rows["expiry"] == exp) & (rows["right"] == "C") & np.isfinite(rows["delta"])]
    if calls.empty:
        return None
    return calls.iloc[(calls["delta"] - 0.5).abs().argsort().iloc[0]]["occ"]
