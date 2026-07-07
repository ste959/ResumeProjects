"""Alpaca historical equity bars → the columnar warehouse.

Pulls split/dividend-adjusted daily bars for a universe of symbols (free IEX feed) and caches
them as Parquet, so the cross-sectional research reads locally without re-hitting the API.

Credentials come from ALPACA_KEY_ID / ALPACA_SECRET_KEY, else from the git-ignored
backend/alpaca-local.yml — the same keys the Java equities module uses. They are never printed
or committed. Swapping to the paid SIP feed later is a one-word change (feed="sip").
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import requests

from . import store

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_URL = "https://data.alpaca.markets/v2/stocks/bars"
EQUITIES_DIR = store.DATA_DIR / "equities"

# A liquid, sector-diverse universe across all 11 GICS sectors — broader than the original 40 so
# the cross-section has some statistical power. Still SURVIVORSHIP-BIASED (today's large caps, no
# delistings / no point-in-time membership): expanding N improves power but does NOT fix selection.
# The sector map doubles as the neutralization classification; UNIVERSE is derived from its keys.
SECTORS = {
    **dict.fromkeys(["AAPL", "MSFT", "NVDA", "AVGO", "AMD", "INTC", "CRM", "ORCL", "CSCO", "QCOM",
                     "TXN", "IBM", "ADBE", "ACN", "NOW", "AMAT", "MU", "LRCX", "ADI", "KLAC",
                     "SNPS", "CDNS", "INTU"], "InfoTech"),
    **dict.fromkeys(["GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS", "CHTR"], "CommSvcs"),
    **dict.fromkeys(["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TJX", "GM", "F",
                     "MAR"], "ConsDisc"),
    **dict.fromkeys(["JPM", "BAC", "WFC", "GS", "MS", "C", "V", "MA", "AXP", "BLK", "SCHW", "SPGI",
                     "CB", "PGR", "USB", "PNC"], "Financials"),
    **dict.fromkeys(["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY"], "Energy"),
    **dict.fromkeys(["JNJ", "UNH", "PFE", "MRK", "ABBV", "LLY", "TMO", "ABT", "DHR", "BMY", "AMGN",
                     "MDT", "GILD", "CVS", "CI"], "HealthCare"),
    **dict.fromkeys(["PG", "KO", "PEP", "WMT", "COST", "MDLZ", "CL", "MO", "PM", "TGT", "KMB",
                     "GIS"], "Staples"),
    **dict.fromkeys(["BA", "CAT", "HON", "UPS", "GE", "RTX", "UNP", "LMT", "DE", "MMM", "EMR",
                     "ADP"], "Industrials"),
    **dict.fromkeys(["NEE", "DUK", "SO", "D", "AEP"], "Utilities"),
    **dict.fromkeys(["AMT", "PLD", "EQIX", "SPG", "O"], "RealEstate"),
    **dict.fromkeys(["LIN", "APD", "SHW", "FCX", "NEM", "ECL"], "Materials"),
}
UNIVERSE = list(SECTORS)


def _credentials() -> tuple[str, str]:
    kid, sec = os.environ.get("ALPACA_KEY_ID"), os.environ.get("ALPACA_SECRET_KEY")
    if kid and sec:
        return kid, sec
    yml = REPO_ROOT / "backend" / "alpaca-local.yml"
    if yml.exists():
        for line in yml.read_text().splitlines():
            s = line.strip()
            if s.startswith("key-id:"):
                kid = s.split(":", 1)[1].strip().strip('"').strip("'")
            elif s.startswith("secret-key:"):
                sec = s.split(":", 1)[1].strip().strip('"').strip("'")
        if kid and sec:
            return kid, sec
    raise RuntimeError(
        "Alpaca credentials not found. Set ALPACA_KEY_ID / ALPACA_SECRET_KEY or put them in "
        "backend/alpaca-local.yml.")


def fetch_bars(symbols, start: str, end: str, timeframe: str = "1Day",
               feed: str = "iex", adjustment: str = "all") -> pd.DataFrame:
    """Fetch bars for one or more symbols over [start, end] (ISO dates), following pagination.

    adjustment='all' applies split + dividend adjustments — without it, the price series is
    fiction (an unadjusted split reads as a 50% crash).
    """
    kid, sec = _credentials()
    headers = {"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec}
    syms = ",".join(symbols) if isinstance(symbols, (list, tuple)) else symbols

    rows: list[dict] = []
    token = None
    while True:
        params = {"symbols": syms, "timeframe": timeframe, "start": start, "end": end,
                  "feed": feed, "adjustment": adjustment, "limit": 10000}
        if token:
            params["page_token"] = token
        resp = requests.get(DATA_URL, headers=headers, params=params, timeout=30)
        if resp.status_code == 429:  # rate limited — back off and retry
            time.sleep(2)
            continue
        resp.raise_for_status()
        data = resp.json()
        for sym, bars in (data.get("bars") or {}).items():
            for b in bars:
                rows.append({"symbol": sym, "ts": b["t"], "open": b["o"], "high": b["h"],
                             "low": b["l"], "close": b["c"], "volume": b["v"],
                             "vwap": b.get("vw"), "trades": b.get("n")})
        token = data.get("next_page_token")
        if not token:
            break

    df = pd.DataFrame(rows)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df = df.sort_values(["symbol", "ts"]).reset_index(drop=True)
    return df


def cache_universe(symbols=None, start: str = "2020-07-27", end: str = "2026-07-02",
                   timeframe: str = "1Day") -> Path:
    """Fetch the universe's bars and write them to the warehouse as one Parquet table.

    Window is the MAX the free IEX feed allows: it hard-caps the earliest bar at 2020-07-27
    (asking earlier returns nothing before it), and extends to ~today — 2020-07-27 .. 2026-07-02 is
    ~1491 trading days (~5.9y). Extending the end adds data with NO extra survivorship bias (that
    comes from the start-date name selection); going earlier needs a paid, point-in-time source."""
    symbols = symbols or UNIVERSE
    df = fetch_bars(symbols, start, end, timeframe=timeframe)
    path = EQUITIES_DIR / f"bars_{timeframe}.parquet"
    store.write_parquet(df, path)
    return path


def load_bars(timeframe: str = "1Day") -> pd.DataFrame:
    """Read the cached bars as a tidy long table (symbol, ts, ohlcv)."""
    return store.read_parquet(EQUITIES_DIR / f"bars_{timeframe}.parquet")


def close_panel(df: pd.DataFrame, field: str = "close") -> pd.DataFrame:
    """Pivot the long bar table into a symbols × dates panel of one field (for cross-section)."""
    return df.pivot(index="ts", columns="symbol", values=field).sort_index()
