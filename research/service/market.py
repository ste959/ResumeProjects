"""Exploration data — screener, technicals, sector rotation, news, and catalysts off the Alpaca feed.

The technical indicators (SMA / RSI / ATR / returns) are computed here from real bars — pure functions
so they're unit-tested without any I/O. The sector view uses real sector-ETF returns (how desks
actually read rotation), and the catalyst rail pairs the fixed FOMC schedule with the live trading
calendar. Everything that reaches the market goes through alpaca.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Sector SPDR ETFs — a real, liquid proxy for sector rotation.
SECTOR_ETFS = [
    ("XLK", "Technology"), ("XLF", "Financials"), ("XLE", "Energy"), ("XLV", "Health Care"),
    ("XLY", "Cons. Discretionary"), ("XLP", "Cons. Staples"), ("XLI", "Industrials"),
    ("XLB", "Materials"), ("XLU", "Utilities"), ("XLRE", "Real Estate"), ("XLC", "Communication"),
]

# 2026 FOMC decision dates (the second, announcement day). Source: federalreserve.gov FOMC calendar.
FOMC_2026 = ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"]

NORMAL_CLOSE = "16:00"


# ── Pure technical indicators (unit-tested) ──────────────────────────────────────────────────────
def _sma(xs: list[float], n: int) -> float | None:
    return sum(xs[-n:]) / n if len(xs) >= n else None


def _rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) <= n:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(d for d in deltas[:n] if d > 0) / n
    avg_loss = sum(-d for d in deltas[:n] if d < 0) / n
    for d in deltas[n:]:                                   # Wilder smoothing
        avg_gain = (avg_gain * (n - 1) + (d if d > 0 else 0)) / n
        avg_loss = (avg_loss * (n - 1) + (-d if d < 0 else 0)) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(bars: list[dict], n: int = 14) -> float | None:
    if len(bars) <= n:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, low, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr


def _ret(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or closes[-n - 1] == 0:
        return None
    return closes[-1] / closes[-n - 1] - 1.0


def compute_technicals(bars: list[dict]) -> dict:
    """SMA/RSI/ATR/returns + trend from a list of daily bars ({o,h,l,c,v,t}). Pure."""
    closes = [float(b["c"]) for b in bars if b.get("c") is not None]
    if len(closes) < 2:
        return {"ok": False}
    last = closes[-1]
    sma20, sma50 = _sma(closes, 20), _sma(closes, 50)
    atr = _atr(bars, 14)
    return {
        "ok": True, "last": last,
        "sma20": sma20, "sma50": sma50,
        "trend": (sma20 is not None and sma50 is not None and sma20 > sma50),
        "rsi14": _rsi(closes, 14), "atr14": atr,
        "atr_pct": (atr / last) if (atr and last) else None,
        "ret_1w": _ret(closes, 5), "ret_1m": _ret(closes, 21), "ret_3m": _ret(closes, 63),
        "hi": max(closes), "lo": min(closes), "n": len(closes),
        "spark": [round(c, 4) for c in closes[-60:]],
    }


# ── Data-fetching views (call Alpaca) ────────────────────────────────────────────────────────────
def _row(item: dict) -> dict:
    return {"symbol": item.get("symbol"), "price": item.get("price"),
            "change": item.get("change"), "percent_change": item.get("percent_change"),
            "volume": item.get("volume"), "trade_count": item.get("trade_count")}


def screener() -> dict:
    from . import alpaca
    actives = alpaca.most_actives(top=20).get("most_actives", [])
    mv = alpaca.movers(top=10)
    return {
        "most_active": [_row(x) for x in actives],
        "gainers": [_row(x) for x in mv.get("gainers", [])],
        "losers": [_row(x) for x in mv.get("losers", [])],
    }


def technicals(symbol: str) -> dict:
    from . import alpaca
    data = alpaca.stock_bars(symbol, timeframe="1Day", limit=180)
    bars = (data.get("bars") or {}).get(symbol) or []
    t = compute_technicals(bars)
    return {"symbol": symbol, **t}


def sectors() -> list[dict]:
    """Latest daily return per sector ETF — real sector-rotation read (snapshots are empty on the free
    IEX feed for these, so derive the move from the last two daily bars)."""
    from . import alpaca
    syms = [s for s, _ in SECTOR_ETFS]
    bars = (alpaca.stock_bars_multi(syms, timeframe="1Day", limit=3).get("bars") or {})
    out = []
    for sym, name in SECTOR_ETFS:
        b = bars.get(sym) or []
        c = b[-1]["c"] if b else None
        pc = b[-2]["c"] if len(b) >= 2 else None
        chg = (c / pc - 1.0) if (c and pc) else None
        out.append({"symbol": sym, "name": name, "price": c, "change": chg})
    out.sort(key=lambda r: (r["change"] is not None, r["change"] or 0), reverse=True)
    return out


def news(symbols: list[str] | None, limit: int = 20) -> list[dict]:
    from . import alpaca
    items = alpaca.news(symbols=symbols, limit=limit).get("news", [])
    out = []
    for n in items:
        out.append({
            "id": n.get("id"), "headline": n.get("headline"), "summary": (n.get("summary") or "")[:240],
            "source": n.get("source"), "url": n.get("url"),
            "created_at": n.get("created_at") or n.get("updated_at"),
            "symbols": n.get("symbols") or [],
        })
    return out


def catalysts() -> dict:
    """Upcoming FOMC decisions (fixed schedule) + the next market holiday & early close (live calendar)."""
    from . import alpaca
    today = datetime.now(timezone.utc).date()
    fomc = [{"date": d, "days_out": (datetime.strptime(d, "%Y-%m-%d").date() - today).days}
            for d in FOMC_2026 if datetime.strptime(d, "%Y-%m-%d").date() >= today][:4]

    next_holiday = next_early_close = None
    try:
        end = today + timedelta(days=80)
        cal = alpaca.calendar(today.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        trading = {c["date"]: c for c in cal}
        for i in range(1, 81):
            d = today + timedelta(days=i)
            ds = d.strftime("%Y-%m-%d")
            if d.weekday() < 5 and ds not in trading and next_holiday is None:
                next_holiday = {"date": ds, "days_out": i}
            c = trading.get(ds)
            if c and c.get("close") and c["close"] < NORMAL_CLOSE and next_early_close is None:
                next_early_close = {"date": ds, "days_out": i, "close": c["close"]}
    except alpaca.AlpacaError:
        pass

    return {"fomc": fomc, "next_holiday": next_holiday, "next_early_close": next_early_close}
