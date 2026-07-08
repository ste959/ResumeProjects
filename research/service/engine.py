"""The live strategy engine — a background loop that trades armed strategies on the paper account.

Safety model:
  • Starts **disarmed**: strategies trade only after an explicit arm(). The loop still runs while
    disarmed, but read-only — it just rebuilds books and marks.
  • A global **kill switch latches**: it halts trading and clears the armed set, and stays engaged
    until an explicit resume() — arming does NOT release it. It is also re-checked immediately before
    every order, so an in-flight cycle stops the instant kill is pressed.
  • Position is **sign-with-hysteresis**: enter on a signal flip to long, hold while long (no
    rebalancing), exit on a flip to flat. This matches the backtest exactly (it, too, only trades on
    sign changes) — no live/backtest turnover drift.
  • Every order is tagged (`client_order_id = qd-{strategy}-{seq}`, seq strictly increasing), so the
    per-strategy book is reconstructed from Alpaca's own order history — no fragile local state.

All account mutation flows through here; strategies.py stays pure.
"""

from __future__ import annotations

import threading
import time
import traceback

from . import alpaca
from . import strategies as S

INTERVAL_SECONDS = 60
MIN_ORDER_USD = 25.0
BAR_TIMEFRAME = "1Hour"
BAR_LIMIT = 120
MAX_ACTIONS = 60

_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_last_seq = 0


def _next_seq() -> int:
    """Strictly-increasing order sequence: wall-clock ms, bumped so it never repeats within the process
    and (because it's clock-based) doesn't collide with a prior run's tags after a restart."""
    global _last_seq
    with _LOCK:
        s = int(time.time() * 1000)
        if s <= _last_seq:
            s = _last_seq + 1
        _last_seq = s
        return s


def _halted(sid: str) -> bool:
    """True if the engine is killed or this strategy is no longer armed — checked right before trading."""
    with _LOCK:
        return _STATE["kill"] or sid not in _STATE["armed"]

_STATE: dict = {
    "armed": set(),          # strategy ids currently trading
    "kill": False,           # global halt
    "last_run": None,        # epoch seconds of the last cycle
    "last_error": None,      # last loop exception (string), if any
    "actions": [],           # recent engine actions (newest first) for the UI log
    "books": [],             # last per-strategy attribution rows
    "marks": {},             # last {symbol: price}
    "running": False,        # is the background loop alive
}


def _all_symbols() -> list[str]:
    seen: list[str] = []
    for d in S.REGISTRY.values():
        for s in d.symbols:
            if s not in seen:
                seen.append(s)
    return seen


def _log(kind: str, msg: str, **extra) -> None:
    entry = {"ts": time.time(), "kind": kind, "msg": msg, **extra}
    with _LOCK:
        _STATE["actions"].insert(0, entry)
        del _STATE["actions"][MAX_ACTIONS:]


def _fills_by_strategy() -> dict[str, dict[str, list[dict]]]:
    """Rebuild every strategy's fills from tagged, filled Alpaca orders (time-ordered per symbol).
    Paginates the full order history so realized P&L never loses an old opening fill (which would
    otherwise leave a sell with no buy and book a phantom short)."""
    orders = alpaca.all_orders()
    grouped: dict[str, dict[str, list[dict]]] = {}
    seen_ids: set = set()
    for o in orders:
        oid = o.get("id")
        if oid in seen_ids:        # de-dup across pagination boundaries (same submitted_at)
            continue
        seen_ids.add(oid)
        sid = S.strategy_of(o.get("client_order_id"))
        if sid is None:
            continue
        fq = float(o.get("filled_qty") or 0)
        fp = o.get("filled_avg_price")
        if fq <= 0 or fp in (None, ""):
            continue
        grouped.setdefault(sid, {}).setdefault(o["symbol"], []).append(
            {"side": o["side"], "qty": fq, "price": float(fp), "ts": o.get("filled_at") or ""})
    for sid in grouped:
        for sym in grouped[sid]:
            grouped[sid][sym].sort(key=lambda f: f["ts"])
    return grouped


def _real_by_symbol(symbols: list[str]) -> dict[str, dict]:
    """Map real Alpaca positions (keyed 'BTCUSD') onto strategy symbols ('BTC/USD') — ground truth.
    Propagates AlpacaError (does NOT return {}): a failed read must NOT read as 'flat', or the engine
    would re-enter a position it already holds. Callers skip trading when this can't be established."""
    rows = alpaca.positions()
    by_norm = {alpaca.position_symbol(p["symbol"]): p for p in rows}
    out: dict[str, dict] = {}
    for sym in symbols:
        p = by_norm.get(alpaca.position_symbol(sym))
        if p:
            out[sym] = {"qty": float(p.get("qty") or 0), "avg_cost": float(p.get("avg_entry_price") or 0),
                        "qty_available": str(p.get("qty_available") or p.get("qty") or "0"),
                        "market_value": float(p.get("market_value") or 0)}
    return out


def refresh() -> tuple[dict, dict, dict | None, list]:
    """Read-only cycle: rebuild books (real holdings + tagged realized) + marks. Never places orders.
    If the real positions read fails, `real` is None — books are left as-is and trading is skipped this
    cycle (fail-safe: never trade against an unknown position)."""
    syms = _all_symbols()
    fbs = _fills_by_strategy()
    marks = alpaca.crypto_marks(syms)
    try:
        real: dict | None = _real_by_symbol(syms)
    except alpaca.AlpacaError:
        real = None
    with _LOCK:
        _STATE["marks"] = marks
        _STATE["last_run"] = time.time()
        if real is not None:
            _STATE["books"] = S.attribute(fbs, real, marks)
        rows = _STATE["books"]
    return fbs, marks, real, rows


def _open_tagged() -> set[tuple[str, str]]:
    """(strategy, symbol) pairs that already have a working (open) tagged order — don't stack on them."""
    try:
        oo = alpaca.orders(status="open", limit=100)
    except alpaca.AlpacaError:
        return set()
    out: set[tuple[str, str]] = set()
    for o in oo:
        sid = S.strategy_of(o.get("client_order_id"))
        if sid:
            out.add((sid, o["symbol"]))
    return out


def _trade_armed(real: dict, marks: dict) -> None:
    """Sign-with-hysteresis: enter full notional on a flip to long, hold while long (NO rebalancing),
    exit on a flip to flat. Re-checks the kill switch / armed set immediately before every order."""
    with _LOCK:
        armed = list(_STATE["armed"])
    pending = _open_tagged()
    for sid in armed:
        defn = S.REGISTRY.get(sid)
        if defn is None:
            continue
        for sym in defn.symbols:
            if (sid, sym) in pending:
                continue  # a prior order is still working — wait for it to fill
            if _halted(sid):
                return    # kill pressed / disarmed mid-cycle — stop before placing anything more
            try:
                closes = alpaca.crypto_closes(sym, timeframe=defn.timeframe, limit=BAR_LIMIT)
                if len(closes) < 5:
                    continue
                sign = S.target_sign(defn, closes)
                px = marks.get(sym) or closes[-1]
                rp = real.get(sym, {})
                cur = float(rp.get("qty", 0.0))
                held = abs(cur) * px >= MIN_ORDER_USD
                if sign == 1 and not held:                         # flip to long → enter
                    qty = round(defn.notional / px - max(cur, 0.0), 6)   # top up any dust, don't stack on it
                    if qty * px < MIN_ORDER_USD:
                        continue
                    if _halted(sid):
                        return
                    alpaca.submit_order(sym, qty, "buy", type_="market", tif="gtc", client_order_id=S.order_tag(sid, _next_seq()))
                    _log("order", f"{sid}: enter buy {qty} {sym} @~{px:.2f}", strategy=sid, symbol=sym, side="buy", qty=qty)
                elif sign == 0 and held:                           # flip to flat → exit the whole position
                    avail = str(rp.get("qty_available") or cur)
                    if float(avail) <= 0:
                        continue
                    if _halted(sid):
                        return
                    alpaca.submit_order(sym, avail, "sell", type_="market", tif="gtc", client_order_id=S.order_tag(sid, _next_seq()))
                    _log("order", f"{sid}: exit sell {avail} {sym} @~{px:.2f}", strategy=sid, symbol=sym, side="sell", qty=float(avail))
                # else: long & signal long → hold; flat & signal flat → nothing (no rebalancing)
            except alpaca.AlpacaError as e:
                _log("error", f"{sid} {sym}: {e}", strategy=sid, symbol=sym)


def run_once() -> None:
    """One engine cycle: refresh books, then (if not killed) trade the armed strategies."""
    try:
        _, marks, real, _ = refresh()
        with _LOCK:
            killed = _STATE["kill"]
            armed = bool(_STATE["armed"])
        if killed or real is None:      # killed, or positions unknown this cycle → don't trade
            return
        if armed:
            _trade_armed(real, marks)
        with _LOCK:
            _STATE["last_error"] = None
    except alpaca.AlpacaError as e:
        with _LOCK:
            _STATE["last_error"] = str(e)
    except Exception:  # noqa: BLE001 — the loop must never die
        with _LOCK:
            _STATE["last_error"] = traceback.format_exc(limit=2)


def _loop() -> None:
    with _LOCK:
        _STATE["running"] = True
    while not _STOP.wait(0.1):
        run_once()
        _STOP.wait(INTERVAL_SECONDS)
    with _LOCK:
        _STATE["running"] = False


def start() -> None:
    """Launch the background loop once, if Alpaca is configured."""
    global _THREAD
    if not alpaca.configured():
        return
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return
        _STOP.clear()
        _THREAD = threading.Thread(target=_loop, name="qd-engine", daemon=True)
        _THREAD.start()


# ── Controls (called from the API) ───────────────────────────────────────────────────────────────
def arm(sid: str) -> None:
    """Arm a strategy. Does NOT release the kill switch — a latched kill must be cleared with resume()
    first, or nothing trades. (Arming while killed just queues it for when kill is released.)"""
    if sid not in S.REGISTRY:
        raise KeyError(sid)
    with _LOCK:
        _STATE["armed"].add(sid)
    _log("arm", f"armed {sid}" + (" (kill still engaged — resume to trade)" if _STATE["kill"] else ""))


def disarm(sid: str) -> None:
    with _LOCK:
        _STATE["armed"].discard(sid)
    _log("disarm", f"disarmed {sid}")


def kill() -> None:
    with _LOCK:
        _STATE["armed"].clear()
        _STATE["kill"] = True
    _log("kill", "KILL — all strategies disarmed")


def resume() -> None:
    with _LOCK:
        _STATE["kill"] = False
    _log("resume", "kill switch released")


def flatten(sid: str) -> None:
    """Close a strategy's open positions (does not disarm it).

    Sells the *real available* balance — not the tagged quantity — because crypto fees make the
    filled quantity slightly overstate what's actually holdable, and over-selling is rejected. The
    closing order is tagged so it's attributed back to the strategy."""
    if sid not in S.REGISTRY:
        raise KeyError(sid)
    defn = S.REGISTRY[sid]
    try:
        real = {alpaca.position_symbol(p["symbol"]): p for p in alpaca.positions()}
    except alpaca.AlpacaError as e:
        _log("error", f"flatten {sid}: {e}")
        return
    for sym in defn.symbols:
        p = real.get(alpaca.position_symbol(sym))
        if not p:
            continue
        qty = float(p.get("qty") or 0)
        # Use Alpaca's exact available string — never round (rounding up over-sells and is rejected).
        avail_str = str(p.get("qty_available") or p.get("qty") or "0")
        if qty == 0 or float(avail_str) <= 0:
            continue
        side = "sell" if qty > 0 else "buy"
        coid = S.order_tag(sid, _next_seq())
        try:
            alpaca.submit_order(sym, avail_str, side, type_="market", tif="gtc", client_order_id=coid)
            _log("flatten", f"{sid}: {side} {avail_str} {sym} to close", strategy=sid, symbol=sym)
        except alpaca.AlpacaError as e:
            _log("error", f"flatten {sid} {sym}: {e}")


def snapshot() -> dict:
    """Everything the Live UI needs in one payload."""
    with _LOCK:
        return {
            "running": _STATE["running"], "kill": _STATE["kill"],
            "armed": sorted(_STATE["armed"]),
            "last_run": _STATE["last_run"], "last_error": _STATE["last_error"],
            "interval": INTERVAL_SECONDS,
            "strategies": _STATE["books"],
            "marks": _STATE["marks"],
            "actions": list(_STATE["actions"]),
        }
