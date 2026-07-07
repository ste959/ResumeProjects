"""Strategy definitions, signal logic, and per-strategy P&L attribution — all pure, no I/O.

The engine (engine.py) submits every order with a `client_order_id` of the form `qd-{strategy}-{n}`,
so a strategy's book can be reconstructed entirely from Alpaca's order history: no fragile local
state, and per-strategy P&L survives restarts. This module owns (a) the strategy registry, (b) the
signal each strategy produces from a price series, and (c) the accounting that turns tagged fills +
current marks into realized/unrealized P&L per strategy. Everything here is deterministic and unit-
tested; the live plumbing lives in engine.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ID_PREFIX = "qd"


@dataclass(frozen=True)
class StrategyDef:
    id: str
    name: str
    desc: str
    asset_class: str          # 'crypto' (24/7) | 'us_equity'
    symbols: tuple[str, ...]
    kind: str                 # 'ma_crossover' | 'momentum'
    params: dict = field(default_factory=dict)
    notional: float = 1000.0  # target gross $ per held symbol when in-position


# The initial book of strategies. Crypto first so the live demo trades around the clock.
REGISTRY: dict[str, StrategyDef] = {
    "btc-trend": StrategyDef(
        id="btc-trend", name="BTC Trend (MA crossover)",
        desc="Long BTC when the fast moving average is above the slow one; flat otherwise. Classic trend-following.",
        asset_class="crypto", symbols=("BTC/USD",), kind="ma_crossover",
        params={"fast": 12, "slow": 48}, notional=1500.0),
    "eth-mom": StrategyDef(
        id="eth-mom", name="ETH Momentum",
        desc="Long ETH when trailing return over the lookback is positive; flat when it rolls over.",
        asset_class="crypto", symbols=("ETH/USD",), kind="momentum",
        params={"lookback": 24}, notional=1500.0),
}


def order_tag(strategy_id: str, seq: int) -> str:
    """Build the client_order_id that stamps an order with its owning strategy."""
    return f"{ID_PREFIX}-{strategy_id}-{seq}"


def strategy_of(client_order_id: str | None) -> str | None:
    """Recover the strategy id from a tagged client_order_id (None if untagged / hand-placed)."""
    if not client_order_id or not client_order_id.startswith(ID_PREFIX + "-"):
        return None
    rest = client_order_id[len(ID_PREFIX) + 1:]
    sid, _, tail = rest.rpartition("-")
    if sid and tail.isdigit() and sid in REGISTRY:
        return sid
    return None


# ── Signals: price series → target position sign (+1 long, 0 flat) ───────────────────────────────
def _sma(xs: list[float], n: int) -> float | None:
    if len(xs) < n or n <= 0:
        return None
    return sum(xs[-n:]) / n


def target_sign(defn: StrategyDef, closes: list[float]) -> int:
    """The desired position direction for a strategy given a close-price series (oldest→newest).
    Long-only for now (0 or +1): these are directional trend/momentum sleeves, not market-neutral."""
    if defn.kind == "ma_crossover":
        fast = _sma(closes, int(defn.params.get("fast", 12)))
        slow = _sma(closes, int(defn.params.get("slow", 48)))
        if fast is None or slow is None:
            return 0
        return 1 if fast > slow else 0
    if defn.kind == "momentum":
        lb = int(defn.params.get("lookback", 24))
        if len(closes) <= lb or closes[-lb - 1] == 0:
            return 0
        return 1 if (closes[-1] / closes[-lb - 1] - 1.0) > 0 else 0
    return 0


def target_qty(defn: StrategyDef, closes: list[float]) -> float:
    """Target position size in units: notional / price when the signal is on, else 0."""
    if not closes:
        return 0.0
    px = closes[-1]
    if px <= 0:
        return 0.0
    return round(defn.notional / px, 6) * target_sign(defn, closes)


# ── Attribution: tagged fills + marks → per-strategy realized/unrealized P&L ──────────────────────
@dataclass
class SymbolBook:
    qty: float = 0.0          # signed position (long +, short −)
    avg_cost: float = 0.0     # average cost of the open position
    realized: float = 0.0     # realized P&L booked on reductions


def apply_fill(book: SymbolBook, side: str, qty: float, price: float) -> SymbolBook:
    """Average-cost accounting for one fill. Booking realized P&L when a position is reduced/flipped."""
    signed = qty if side == "buy" else -qty
    pos = book.qty
    if pos == 0 or (pos > 0) == (signed > 0):
        # opening or adding in the same direction → blend average cost
        new_qty = pos + signed
        if new_qty != 0:
            book.avg_cost = (book.avg_cost * abs(pos) + price * abs(signed)) / abs(new_qty)
        book.qty = new_qty
        return book
    # reducing or flipping: realize on the closed portion
    closing = min(abs(signed), abs(pos))
    direction = 1 if pos > 0 else -1
    book.realized += closing * (price - book.avg_cost) * direction
    remaining = abs(signed) - closing
    book.qty = pos + signed
    if abs(pos) > closing:            # still open in the original direction; avg_cost unchanged
        return book
    # fully closed (and maybe flipped); the flipped remainder opens at this price
    book.avg_cost = price if remaining > 0 else 0.0
    return book


def position_pnl(fills: list[dict], mark: float | None) -> dict:
    """Reduce a symbol's fills (each {side, qty, price}, time-ordered) to realized + unrealized P&L."""
    book = SymbolBook()
    for f in fills:
        if f.get("price") is None or f.get("qty") in (None, 0):
            continue
        apply_fill(book, f["side"], float(f["qty"]), float(f["price"]))
    unreal = 0.0
    if mark is not None and book.qty != 0:
        unreal = book.qty * (mark - book.avg_cost)
    return {"qty": book.qty, "avg_cost": book.avg_cost,
            "realized": book.realized, "unrealized": unreal,
            "market_value": (book.qty * mark) if mark is not None else 0.0}


def attribute(fills_by_strategy: dict[str, dict[str, list[dict]]],
              real_by_symbol: dict[str, dict]) -> list[dict]:
    """Per-strategy P&L rollup — holdings from reality, realized from the tag record.

    `fills_by_strategy`: {strategy_id: {symbol: [fill, ...]}} (tagged fills, for realized P&L).
    `real_by_symbol`: {symbol: {qty, avg_cost, unrealized, market_value}} — the *real* Alpaca position,
    the ground truth for live holdings (fee-exact, and self-healing if a position is touched outside the
    tags). Live qty / unrealized / market value come from there; realized comes from round-trips in the
    tagged fills. Returns one row per registered strategy (even untouched ones) so the UI shows the full book.
    """
    rows = []
    for sid, defn in REGISTRY.items():
        by_symbol = fills_by_strategy.get(sid, {})
        positions, realized, unrealized, gross = [], 0.0, 0.0, 0.0
        for sym in defn.symbols:
            fills = by_symbol.get(sym, [])
            realized_sym = position_pnl(fills, None)["realized"]      # from the tagged round-trips
            rp = real_by_symbol.get(sym) or {}
            qty = float(rp.get("qty", 0.0))
            avg_cost = float(rp.get("avg_cost", 0.0))
            unreal_sym = float(rp.get("unrealized", 0.0))
            mv = float(rp.get("market_value", 0.0))
            realized += realized_sym
            unrealized += unreal_sym
            gross += abs(mv)
            if qty != 0:                                          # only actually-open positions
                positions.append({"symbol": sym, "qty": qty, "avg_cost": avg_cost,
                                  "realized": realized_sym, "unrealized": unreal_sym,
                                  "market_value": mv, "n_fills": len(fills)})
        rows.append({
            "id": sid, "name": defn.name, "desc": defn.desc,
            "asset_class": defn.asset_class, "kind": defn.kind, "symbols": list(defn.symbols),
            "realized": realized, "unrealized": unrealized, "total_pnl": realized + unrealized,
            "gross_exposure": gross, "positions": positions,
            "n_fills": sum(len(by_symbol.get(s, [])) for s in defn.symbols),
        })
    return rows
