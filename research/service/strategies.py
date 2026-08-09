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
    timeframe: str = "1Hour"  # bar timeframe the live signal is computed on
    promoted: bool = False    # created from a backtest (vs a seed strategy)


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


def register(kind: str, symbol: str, timeframe: str, params: dict, notional: float = 1000.0) -> "StrategyDef":
    """Promote a backtested config into the live registry (idempotent). Crypto only — the engine trades
    24/7 crypto; equities would need market-hours + a separate order path."""
    if kind not in {"ma_crossover", "momentum"}:
        raise ValueError(f"unknown strategy kind: {kind}")
    if "/" not in symbol:
        raise ValueError("only crypto strategies can go live for now")
    if not (0 < notional <= 100_000):
        raise ValueError("notional must be between 0 and 100,000")
    pslug = "-".join(str(params[k]) for k in sorted(params))
    sid = f"{kind.split('_')[0]}-{symbol.split('/')[0].lower()}-{pslug}"
    if sid in REGISTRY:
        return REGISTRY[sid]
    label = "MA-cross" if kind == "ma_crossover" else "Momentum"
    defn = StrategyDef(
        id=sid, name=f"{label} {symbol} ({pslug})",
        desc=f"Promoted from the backtest lab: {kind.replace('_', ' ')} on {symbol} {timeframe} bars, params {params}.",
        asset_class="crypto", symbols=(symbol,), kind=kind, params=dict(params),
        notional=notional, timeframe=timeframe, promoted=True)
    REGISTRY[sid] = defn
    return defn


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


# Alpaca crypto taker fee (lowest tier). Calibrated to the ~0.25% in-kind drift we observed live —
# every fill pays it, so it belongs in the cost basis (buys) and the proceeds (sells).
CRYPTO_FEE_RATE = 0.0025


def apply_fill(book: SymbolBook, side: str, qty: float, price: float, fee_rate: float = 0.0) -> SymbolBook:
    """Average-cost accounting for one fill, net of a per-side fee. Books realized P&L on a reduction/
    flip. Fees raise the cost basis on the entering leg and cut the proceeds on the exiting leg, so no
    trade is free — the omission a trader would flag first."""
    signed = qty if side == "buy" else -qty
    pos = book.qty
    if pos == 0 or (pos > 0) == (signed > 0):
        # opening or adding in the same direction → blend average cost (fee-inclusive)
        eff = price * (1 + fee_rate) if signed > 0 else price * (1 - fee_rate)
        new_qty = pos + signed
        if new_qty != 0:
            book.avg_cost = (book.avg_cost * abs(pos) + eff * abs(signed)) / abs(new_qty)
        book.qty = new_qty
        return book
    # reducing or flipping: realize on the closed portion at the fee-adjusted exit price
    closing = min(abs(signed), abs(pos))
    direction = 1 if pos > 0 else -1
    exit_px = price * (1 - fee_rate) if direction > 0 else price * (1 + fee_rate)
    book.realized += closing * (exit_px - book.avg_cost) * direction
    remaining = abs(signed) - closing
    book.qty = pos + signed
    if abs(pos) > closing:            # still open in the original direction; avg_cost unchanged
        return book
    # fully closed (and maybe flipped); the flipped remainder opens (fee-inclusive) at this price
    book.avg_cost = (price * (1 + fee_rate) if signed > 0 else price * (1 - fee_rate)) if remaining > 0 else 0.0
    return book


def position_pnl(fills: list[dict], mark: float | None, fee_rate: float = 0.0) -> dict:
    """Reduce a symbol's fills (each {side, qty, price}, time-ordered) to realized + unrealized P&L,
    net of `fee_rate` per side."""
    book = SymbolBook()
    for f in fills:
        if f.get("price") is None or f.get("qty") in (None, 0):
            continue
        apply_fill(book, f["side"], float(f["qty"]), float(f["price"]), fee_rate=fee_rate)
    unreal = 0.0
    if mark is not None and book.qty != 0:
        unreal = book.qty * (mark - book.avg_cost)
    return {"qty": book.qty, "avg_cost": book.avg_cost,
            "realized": book.realized, "unrealized": unreal,
            "market_value": (book.qty * mark) if mark is not None else 0.0}


def attribute(fills_by_strategy: dict[str, dict[str, list[dict]]],
              real_by_symbol: dict[str, dict], marks: dict[str, float] | None = None,
              fee_rate: float = CRYPTO_FEE_RATE) -> list[dict]:
    """Per-strategy P&L rollup — realized from the tag record, holdings reconciled to reality.

    `fills_by_strategy`: {strategy_id: {symbol: [fill]}} (tagged fills → per-strategy book, fee-net).
    `real_by_symbol`: {symbol: {qty, ...}} — the *real* Alpaca position (ground truth for the total held
    per symbol). `marks`: {symbol: price} for mark-to-market.

    When several strategies hold the same symbol, the single real position is **split across them
    pro-rata by each strategy's tagged quantity** (not handed in full to each — the bug a reviewer would
    catch), and the split absorbs fee drift so the parts sum to reality. If the real position is flat, a
    stale tagged book self-heals to zero. Realized (fee-inclusive) comes from the tagged round-trips.
    """
    marks = marks or {}

    # Pass 1: each strategy's own tagged book per symbol, and the total tagged qty per symbol.
    books: dict[tuple[str, str], dict] = {}
    tagged_sum: dict[str, float] = {}
    for sid, defn in REGISTRY.items():
        for sym in defn.symbols:
            b = position_pnl(fills_by_strategy.get(sid, {}).get(sym, []), None, fee_rate=fee_rate)
            books[(sid, sym)] = b
            tagged_sum[sym] = tagged_sum.get(sym, 0.0) + b["qty"]

    # Pass 2: reconcile each strategy's share of the real position and mark it.
    rows = []
    for sid, defn in REGISTRY.items():
        by_symbol = fills_by_strategy.get(sid, {})
        positions, realized, unrealized, gross = [], 0.0, 0.0, 0.0
        for sym in defn.symbols:
            b = books[(sid, sym)]
            realized += b["realized"]
            real_total = float((real_by_symbol.get(sym) or {}).get("qty", 0.0))
            s = tagged_sum.get(sym, 0.0)
            # Split the real position pro-rata by tagged qty. Guard a *near-zero* denominator (not just
            # exact 0): if two strategies ever held offsetting tagged positions that net to ~0, dividing
            # by it would explode every strategy's reconciled qty — treat as unattributable instead.
            scale = (real_total / s) if abs(s) > 1e-9 else 0.0
            qty = b["qty"] * scale                                # this strategy's reconciled holding
            mark = marks.get(sym)
            # Unrealized is the *liquidation* value: mark net of the exit fee you'd pay to close, so the
            # figure is genuinely net of fees (not just the entry fee baked into avg_cost).
            net_mark = mark * (1 - (fee_rate if qty > 0 else -fee_rate)) if mark is not None else None
            unreal = qty * (net_mark - b["avg_cost"]) if (net_mark is not None and qty != 0) else 0.0
            mv = qty * mark if (mark is not None) else 0.0
            unrealized += unreal
            gross += abs(mv)
            if qty != 0:
                positions.append({"symbol": sym, "qty": qty, "avg_cost": b["avg_cost"],
                                  "realized": b["realized"], "unrealized": unreal,
                                  "market_value": mv, "n_fills": len(by_symbol.get(sym, []))})
        rows.append({
            "id": sid, "name": defn.name, "desc": defn.desc,
            "asset_class": defn.asset_class, "kind": defn.kind, "symbols": list(defn.symbols),
            "promoted": defn.promoted,
            "realized": realized, "unrealized": unrealized, "total_pnl": realized + unrealized,
            "gross_exposure": gross, "positions": positions,
            "n_fills": sum(len(by_symbol.get(s, [])) for s in defn.symbols),
        })
    return rows
