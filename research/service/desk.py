"""Quant Desk API — the fresh research→backtest→live product, backed by Alpaca paper trading.

This router is the clean-slate surface (separate from the older factor/microstructure endpoints in
`app.py`). Phase 1 ships the Live backbone: a connection/account status the UI gates on, plus live
positions, recent orders, and the portfolio P&L curve — all real reads from the paper account.
Everything degrades to a `configured: false` payload when no keys are present, so the front end shows
a "connect Alpaca" state rather than an error.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query

from . import alpaca
from . import engine
from . import lab
from . import market
from . import strategies as S

router = APIRouter(prefix="/api/research", tags=["desk"])

# Opt-in auth: if QD_API_TOKEN is set in the environment, every state-changing endpoint (arm/disarm/
# flatten/kill/resume/promote) requires a matching `X-QD-Token` header. Unset (the local demo) → open,
# so the desk works out of the box; set it in any shared/hosted deployment to lock down order control.
QD_API_TOKEN = os.environ.get("QD_API_TOKEN", "").strip()


def require_token(x_qd_token: str | None = Header(default=None)) -> None:
    if QD_API_TOKEN and x_qd_token != QD_API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing X-QD-Token")


auth = [Depends(require_token)]   # attach to mutating routes


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


# ── Live strategy engine ─────────────────────────────────────────────────────────────────────────
@router.get("/strategies")
def strategies() -> dict:
    """Per-strategy attribution + engine state (armed set, kill switch, action log)."""
    if not alpaca.configured():
        return {"configured": False, "running": False, "strategies": [], "armed": [], "actions": []}
    return {"configured": True, **engine.snapshot()}


@router.post("/strategies/{sid}/arm", dependencies=auth)
def arm(sid: str) -> dict:
    try:
        engine.arm(sid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown strategy: {sid}")
    return {"ok": True, **engine.snapshot()}


@router.post("/strategies/{sid}/disarm", dependencies=auth)
def disarm(sid: str) -> dict:
    engine.disarm(sid)
    return {"ok": True, **engine.snapshot()}


@router.post("/strategies/{sid}/flatten", dependencies=auth)
def flatten(sid: str) -> dict:
    try:
        engine.flatten(sid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown strategy: {sid}")
    return {"ok": True, **engine.snapshot()}


@router.post("/strategies/kill", dependencies=auth)
def kill() -> dict:
    engine.kill()
    return {"ok": True, **engine.snapshot()}


@router.post("/strategies/resume", dependencies=auth)
def resume() -> dict:
    engine.resume()
    return {"ok": True, **engine.snapshot()}


# ── Backtest lab (research → backtest → promote to live) ─────────────────────────────────────────
@router.get("/lab/templates")
def lab_templates() -> dict:
    """The strategy templates (with param schemas + code) and the testable universe."""
    return {"templates": lab.TEMPLATES, "universe": lab.UNIVERSE,
            "timeframes": list(lab.BARS_PER_YEAR.keys())}


@router.get("/lab/backtest")
def lab_backtest(kind: str = Query(...), symbol: str = Query(...), timeframe: str = Query("1Hour"),
                 cost_bps: float = Query(25.0, ge=0.0, le=200.0),
                 fast: int = Query(12), slow: int = Query(48), lookback: int = Query(24)) -> dict:
    """Run one parameterized, cost-aware backtest over real Alpaca history."""
    params = {"fast": fast, "slow": slow} if kind == "ma_crossover" else {"lookback": lookback}
    try:
        return lab.backtest(kind, symbol, timeframe, params, cost_bps=cost_bps)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown template: {kind}")
    except alpaca.AlpacaError as e:
        raise HTTPException(status_code=502, detail=f"market data error: {e}")


@router.get("/lab/walkforward")
def lab_walkforward(kind: str = Query(...), symbol: str = Query(...), timeframe: str = Query("1Hour"),
                    cost_bps: float = Query(25.0, ge=0.0, le=200.0)) -> dict:
    """Anchored walk-forward: select params in-sample per fold, trade the next window out-of-sample."""
    try:
        return lab.walk_forward(kind, symbol, timeframe, cost_bps)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown template: {kind}")
    except alpaca.AlpacaError as e:
        raise HTTPException(status_code=502, detail=f"market data error: {e}")


@router.post("/lab/promote", dependencies=auth)
def lab_promote(body: dict = Body(...)) -> dict:
    """Register a config as a live strategy — but only after it clears the walk-forward here on the
    SERVER (not just in the UI). The out-of-sample validation is re-run and the params it selected are
    what gets registered, so the gate is a real invariant a direct API call can't bypass."""
    kind = body.get("kind")
    symbol = body.get("symbol")
    timeframe = body.get("timeframe", "1Hour")
    try:
        notional = float(body.get("notional", 1500.0))
        wf = lab.walk_forward(kind, symbol, timeframe, cost_bps=lab.LIVE_TAKER_BPS)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown template: {kind}")
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except alpaca.AlpacaError as e:
        raise HTTPException(status_code=502, detail=f"market data error: {e}")
    if not wf.get("ok"):
        raise HTTPException(status_code=400, detail=wf.get("reason", "walk-forward could not run"))
    if not wf.get("passes"):
        raise HTTPException(status_code=400,
                            detail=f"does not clear out-of-sample walk-forward (OOS Sharpe {wf.get('net_sharpe')})")
    params = wf["folds"][-1]["params"]              # register the params the walk-forward last selected
    try:
        defn = S.register(kind, symbol, timeframe, params, notional=notional)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    engine.refresh()
    return {"ok": True, "strategy_id": defn.id, "name": defn.name,
            "oos_sharpe": wf.get("net_sharpe"), "params": params, **engine.snapshot()}


# ── Exploration (screener · technicals · sectors · news · catalysts) ──────────────────────────────
def _guard_configured():
    if not alpaca.configured():
        raise HTTPException(status_code=503, detail="Alpaca not configured")


@router.get("/market/screener")
def market_screener() -> dict:
    _guard_configured()
    try:
        return market.screener()
    except alpaca.AlpacaError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/market/technicals")
def market_technicals(symbol: str = Query(...)) -> dict:
    _guard_configured()
    try:
        return market.technicals(symbol.upper())
    except alpaca.AlpacaError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/market/sectors")
def market_sectors() -> list[dict]:
    _guard_configured()
    try:
        return market.sectors()
    except alpaca.AlpacaError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/market/news")
def market_news(symbols: str = Query(""), limit: int = Query(20, ge=1, le=50)) -> list[dict]:
    _guard_configured()
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()] or None
    try:
        return market.news(syms, limit=limit)
    except alpaca.AlpacaError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/market/catalysts")
def market_catalysts() -> dict:
    _guard_configured()
    return market.catalysts()
