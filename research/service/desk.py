"""Quant Desk API — the fresh research→backtest→live product, backed by Alpaca paper trading.

This router is the clean-slate surface (separate from the older factor/microstructure endpoints in
`app.py`). Phase 1 ships the Live backbone: a connection/account status the UI gates on, plus live
positions, recent orders, and the portfolio P&L curve — all real reads from the paper account.
Everything degrades to a `configured: false` payload when no keys are present, so the front end shows
a "connect Alpaca" state rather than an error.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import alpaca

router = APIRouter(prefix="/api/research", tags=["desk"])


def _f(x, default: float | None = 0.0) -> float | None:
    """Alpaca returns numbers as strings; coerce, tolerating None/blank."""
    if x is None or x == "":
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


@router.get("/status")
def status() -> dict:
    """Connection gate + account snapshot + market clock. Never raises — the UI reads the flags."""
    if not alpaca.configured():
        return {"configured": False, "connected": False,
                "hint": "Set ALPACA_API_KEY / ALPACA_API_SECRET in the repo .env, then restart the service."}
    try:
        a = alpaca.account()
        c = alpaca.clock()
    except alpaca.AlpacaError as e:
        return {"configured": True, "connected": False, "error": str(e),
                "hint": "Keys are set but the call failed — check they're valid paper-trading keys."}
    equity, last_equity = _f(a.get("equity")), _f(a.get("last_equity"))
    pl_today = (equity or 0.0) - (last_equity or 0.0)
    return {
        "configured": True, "connected": True,
        "account": {
            "status": a.get("status"), "currency": a.get("currency", "USD"),
            "equity": equity, "last_equity": last_equity,
            "cash": _f(a.get("cash")), "buying_power": _f(a.get("buying_power")),
            "portfolio_value": _f(a.get("portfolio_value")),
            "long_mv": _f(a.get("long_market_value")), "short_mv": _f(a.get("short_market_value")),
            "pl_today": pl_today,
            "pl_today_pct": (pl_today / last_equity) if last_equity else 0.0,
            "daytrade_count": a.get("daytrade_count"), "pattern_day_trader": a.get("pattern_day_trader"),
        },
        "clock": {"is_open": c.get("is_open"), "next_open": c.get("next_open"),
                  "next_close": c.get("next_close"), "timestamp": c.get("timestamp")},
    }


@router.get("/live/positions")
def live_positions() -> list[dict]:
    """Open paper positions, marked to the current price."""
    if not alpaca.configured():
        return []
    try:
        rows = alpaca.positions()
    except alpaca.AlpacaError:
        return []
    return [{
        "symbol": p.get("symbol"), "asset_class": p.get("asset_class"), "side": p.get("side"),
        "qty": _f(p.get("qty")), "avg_entry": _f(p.get("avg_entry_price")),
        "current_price": _f(p.get("current_price")), "market_value": _f(p.get("market_value")),
        "cost_basis": _f(p.get("cost_basis")), "unrealized_pl": _f(p.get("unrealized_pl")),
        "unrealized_plpc": _f(p.get("unrealized_plpc")), "change_today": _f(p.get("change_today")),
    } for p in rows]


@router.get("/live/orders")
def live_orders(limit: int = 25) -> list[dict]:
    """Recent orders (any status), newest first."""
    if not alpaca.configured():
        return []
    try:
        rows = alpaca.orders(status="all", limit=limit)
    except alpaca.AlpacaError:
        return []
    return [{
        "id": o.get("id"), "symbol": o.get("symbol"), "side": o.get("side"),
        "qty": _f(o.get("qty")), "filled_qty": _f(o.get("filled_qty")),
        "type": o.get("type"), "status": o.get("status"),
        "submitted_at": o.get("submitted_at"), "filled_at": o.get("filled_at"),
        "filled_avg_price": _f(o.get("filled_avg_price"), default=None),
        "client_order_id": o.get("client_order_id"),
    } for o in rows]


@router.get("/live/history")
def live_history(period: str = "1M", timeframe: str = "1D") -> dict:
    """The paper account's equity curve (portfolio P&L over time) for the Live header chart."""
    if not alpaca.configured():
        return {"configured": False, "base_value": None, "points": []}
    try:
        h = alpaca.portfolio_history(period=period, timeframe=timeframe)
    except alpaca.AlpacaError as e:
        return {"configured": True, "error": str(e), "base_value": None, "points": []}
    ts = h.get("timestamp", []) or []
    eq = h.get("equity", []) or []
    pl = h.get("profit_loss", []) or []
    points = [{"t": int(ts[i]), "equity": _f(eq[i]), "pl": _f(pl[i] if i < len(pl) else None, default=None)}
              for i in range(min(len(ts), len(eq))) if eq[i] is not None]
    return {"configured": True, "base_value": _f(h.get("base_value")), "timeframe": timeframe, "points": points}
