"""Thin Alpaca client — the single real backbone for the quant desk.

One vendor powers all three tabs: market data + news (Exploration), historical bars (Backtest), and
paper trading (Live). Credentials come from the environment (ALPACA_API_KEY / ALPACA_API_SECRET);
with none set the client reports `configured() == False` so the UI can prompt for keys instead of
erroring. Deliberately dependency-light: direct REST over httpx, no SDK, so every call is legible.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx

TRADING_BASE = os.environ.get("ALPACA_TRADING_BASE", "https://paper-api.alpaca.markets")
DATA_BASE = os.environ.get("ALPACA_DATA_BASE", "https://data.alpaca.markets")

_client = httpx.Client(timeout=12.0)


class AlpacaError(RuntimeError):
    """A failed Alpaca call (auth, rate limit, bad request) — carries the status for the UI."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _key() -> str:
    return os.environ.get("ALPACA_API_KEY", "").strip()


def _secret() -> str:
    return os.environ.get("ALPACA_API_SECRET", "").strip()


def configured() -> bool:
    """True once both credentials are present — the gate the UI checks before promising live data."""
    return bool(_key() and _secret())


def _headers() -> dict[str, str]:
    return {"APCA-API-KEY-ID": _key(), "APCA-API-SECRET-KEY": _secret()}


def _get(base: str, path: str, params: dict | None = None) -> dict:
    if not configured():
        raise AlpacaError("Alpaca keys not configured", status=None)
    try:
        r = _client.get(base + path, headers=_headers(), params=params)
    except httpx.HTTPError as e:
        raise AlpacaError(f"network error: {e}", status=None) from e
    if r.status_code >= 400:
        raise AlpacaError(f"{r.status_code} {r.text[:180]}", status=r.status_code)
    return r.json()


def _post(base: str, path: str, body: dict) -> dict:
    if not configured():
        raise AlpacaError("Alpaca keys not configured", status=None)
    try:
        r = _client.post(base + path, headers=_headers(), json=body)
    except httpx.HTTPError as e:
        raise AlpacaError(f"network error: {e}", status=None) from e
    if r.status_code >= 400:
        raise AlpacaError(f"{r.status_code} {r.text[:180]}", status=r.status_code)
    return r.json()


def _delete(base: str, path: str) -> dict:
    if not configured():
        raise AlpacaError("Alpaca keys not configured", status=None)
    try:
        r = _client.delete(base + path, headers=_headers())
    except httpx.HTTPError as e:
        raise AlpacaError(f"network error: {e}", status=None) from e
    if r.status_code >= 400:
        raise AlpacaError(f"{r.status_code} {r.text[:180]}", status=r.status_code)
    return r.json() if r.text else {}


def position_symbol(symbol: str) -> str:
    """Positions/close endpoints use the slashless form (BTC/USD → BTCUSD); orders & data use the slash."""
    return symbol.replace("/", "")


def close_position(symbol: str) -> dict:
    """Close the entire real position for a symbol (fee-exact — avoids over-selling from fee drift)."""
    return _delete(TRADING_BASE, f"/v2/positions/{position_symbol(symbol)}")


# ── Trading (paper) ────────────────────────────────────────────────────────────────────────────
def account() -> dict:
    return _get(TRADING_BASE, "/v2/account")


def clock() -> dict:
    return _get(TRADING_BASE, "/v2/clock")


def positions() -> list[dict]:
    return _get(TRADING_BASE, "/v2/positions")  # type: ignore[return-value]


def orders(status: str = "all", limit: int = 50) -> list[dict]:
    return _get(TRADING_BASE, "/v2/orders",  # type: ignore[return-value]
                {"status": status, "limit": limit, "direction": "desc", "nested": "true"})


def portfolio_history(period: str = "1M", timeframe: str = "1D") -> dict:
    return _get(TRADING_BASE, "/v2/account/portfolio/history",
                {"period": period, "timeframe": timeframe, "extended_hours": "true"})


def submit_order(symbol: str, qty: float | str, side: str, type_: str = "market",
                 tif: str = "gtc", client_order_id: str | None = None) -> dict:
    body: dict = {"symbol": symbol, "qty": str(qty), "side": side, "type": type_, "time_in_force": tif}
    if client_order_id:
        body["client_order_id"] = client_order_id
    return _post(TRADING_BASE, "/v2/orders", body)


# ── Market data ────────────────────────────────────────────────────────────────────────────────
def stock_snapshots(symbols: list[str]) -> dict:
    return _get(DATA_BASE, "/v2/stocks/snapshots", {"symbols": ",".join(symbols), "feed": "iex"})


def stock_bars(symbol: str, timeframe: str = "1Day", limit: int = 120) -> dict:
    return _get(DATA_BASE, "/v2/stocks/bars",
                {"symbols": symbol, "timeframe": timeframe, "limit": limit, "feed": "iex"})


def most_actives(top: int = 25) -> dict:
    return _get(DATA_BASE, "/v1beta1/screener/stocks/most-actives", {"top": top})


def movers(top: int = 15) -> dict:
    return _get(DATA_BASE, "/v1beta1/screener/stocks/movers", {"top": top})


def news(symbols: list[str] | None = None, limit: int = 20) -> dict:
    params: dict = {"limit": limit, "sort": "desc"}
    if symbols:
        params["symbols"] = ",".join(symbols)
    return _get(DATA_BASE, "/v1beta1/news", params)


# ── Crypto market data (24/7 — the live-strategy asset) ──────────────────────────────────────────
# Hours of history one bar spans, so we can request a `start` far enough back to fill `limit` bars
# (Alpaca defaults to start-of-day without one, which starves the moving averages).
_TF_HOURS = {"1Min": 1 / 60, "5Min": 5 / 60, "15Min": 0.25, "1Hour": 1.0, "4Hour": 4.0, "1Day": 24.0}


def crypto_bars(symbols: list[str], timeframe: str = "1Hour", limit: int = 120,
                start: str | None = None) -> dict:
    params: dict = {"symbols": ",".join(symbols), "timeframe": timeframe, "limit": limit}
    if start is None:
        span_h = _TF_HOURS.get(timeframe, 1.0) * (limit + 8)
        start = (datetime.now(timezone.utc) - timedelta(hours=span_h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params["start"] = start
    return _get(DATA_BASE, "/v1beta3/crypto/us/bars", params)


def crypto_snapshots(symbols: list[str]) -> dict:
    return _get(DATA_BASE, "/v1beta3/crypto/us/snapshots", {"symbols": ",".join(symbols)})


def crypto_marks(symbols: list[str]) -> dict[str, float]:
    """Latest trade price per crypto symbol — the mark for P&L and order sizing."""
    snap = crypto_snapshots(symbols)
    book = snap.get("snapshots", snap) or {}
    out: dict[str, float] = {}
    for sym in symbols:
        s = book.get(sym) or {}
        trade = s.get("latestTrade") or s.get("dailyBar") or {}
        px = trade.get("p") or trade.get("c")
        if px is not None:
            out[sym] = float(px)
    return out


def crypto_closes(symbol: str, timeframe: str = "1Hour", limit: int = 120) -> list[float]:
    """Close-price series (oldest→newest) for a crypto symbol — the input to strategy signals."""
    data = crypto_bars([symbol], timeframe=timeframe, limit=limit)
    bars = (data.get("bars") or {}).get(symbol) or []
    return [float(b["c"]) for b in bars if b.get("c") is not None]
