"""Data sources for research: historical Coinbase candles (fetched once, then cached as
Parquet in the DuckDB/Parquet warehouse) and the append-only capture log written by the
Java `MarketRecorder`."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from . import store

CANDLE_URL = "https://api.exchange.coinbase.com/products/{product}/candles"
_HEADERS = {"User-Agent": "bonddesk-research/1.0"}


def _fetch_candles(product: str, granularity: int, pages: int) -> pd.DataFrame:
    """Page backwards through Coinbase's ≤300-row candle endpoint to assemble history."""
    closes: dict[datetime, float] = {}
    end = datetime.now(timezone.utc)
    span = timedelta(seconds=granularity * 300)
    for _ in range(pages):
        start = end - span
        resp = requests.get(
            CANDLE_URL.format(product=product),
            params={"granularity": granularity, "start": start.isoformat(), "end": end.isoformat()},
            headers=_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()  # [[time, low, high, open, close, volume], ...] newest first
        if not rows:
            break
        for t, _low, _high, _open, close, _vol in rows:
            closes[datetime.fromtimestamp(t, tz=timezone.utc)] = float(close)
        end = min(datetime.fromtimestamp(r[0], tz=timezone.utc) for r in rows)
        time.sleep(0.25)  # be polite to the public endpoint
    df = pd.DataFrame({"time": list(closes.keys()), "close": list(closes.values())})
    return df.sort_values("time").reset_index(drop=True)


def candles(product: str, granularity: int = 3600, pages: int = 4, refresh: bool = False) -> pd.Series:
    """Close-price history for a product, cached as Parquet in the warehouse."""
    path = store.candles_path(product, granularity)
    if refresh or not path.exists():
        store.write_parquet(_fetch_candles(product, granularity, pages), path)
    df = store.read_parquet(path)
    s = pd.Series(df["close"].to_numpy(), index=pd.to_datetime(df["time"], utc=True), name=product)
    s.index.name = "time"
    return s


def aligned_closes(products: list[str], granularity: int = 3600, pages: int = 4,
                   refresh: bool = False) -> pd.DataFrame:
    """Close prices for several products aligned on common timestamps (via the cache)."""
    series = [candles(p, granularity, pages, refresh) for p in products]
    return pd.concat(series, axis=1, join="inner").dropna()


def load_capture(csv_glob: str = "market-data/quotes-*.csv") -> pd.DataFrame:
    """Query the Java recorder's capture log with DuckDB (SQL over the raw CSV)."""
    return store.query(
        f"SELECT * FROM read_csv_auto('{csv_glob}', header=true) ORDER BY ts"
    )
