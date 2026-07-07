"""Tax-aware rebalancing — lot-level accounting, loss harvesting, wash sales, holding periods.

For a taxable, medium-to-long-horizon book, *after-tax* return is what compounds — and it is a
genuine, low-variance source of edge that does not need a statistically-significant alpha to be
real. Two levers, both modelled here at the tax-LOT level (every purchase is its own lot with its
own basis and open date, the unit US tax law actually operates on):

  * LOT SELECTION on sells. When a target trim requires selling shares, *which* lots you deliver
    decides the realized gain. HIFO (highest-cost-first) realizes the smallest gains — deferring
    tax (deferral is an interest-free loan from the Treasury) and pushing gains toward the >1-year
    LONG-TERM rate (≈20% vs ≈37% short-term). Naive FIFO does the opposite. The after-tax gap
    between the two, on the *same* pre-tax book, is the "tax alpha".
  * LOSS HARVESTING + WASH SALES. Realizing losses offsets gains, but the wash-sale rule disallows
    a loss if the same security is (re)bought within ±30 days — the constraint that makes naive
    "sell the loser and buy it right back" harvesting illegal. We flag disallowed losses honestly
    rather than booking a benefit the IRS would deny.

Scope & honesty. This simulates the LONG book (weights ≥ 0): shorts are marked-to-market annually
under different rules (§1259 constructive sales, no long-term rate), so lumping them in would be
wrong — the long sleeve is where lot-level tax management applies. The US rate/holding-period
numbers are defaults you pass in. It complements the Java backtest tax engine (Phase 3.5, lot
accounting + §475(f) MTM) one layer up — this is the research-side, factor-book version.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

LONG_TERM_DAYS = 365
DEFAULT_ST_RATE = 0.37     # top US ordinary/short-term rate
DEFAULT_LT_RATE = 0.20     # top US long-term capital-gains rate


@dataclass
class Lot:
    open_date: pd.Timestamp
    shares: float
    cost: float            # per-share basis


@dataclass
class RealizedEvent:
    date: pd.Timestamp
    symbol: str
    shares: float
    proceeds: float
    basis: float
    holding_days: int
    long_term: bool
    disallowed: bool = False      # set by wash-sale post-processing

    @property
    def gain(self) -> float:
        return self.proceeds - self.basis


@dataclass
class SimResult:
    method: str
    events: list[RealizedEvent]
    buys: list[tuple]                       # (date, symbol) repurchase ledger for wash-sale checks
    final_positions: dict                   # symbol -> (shares, market_value, unrealized_gain)
    unrealized_gain: float = 0.0
    tax: dict = field(default_factory=dict)


def _lot_order(lots: list[Lot], method: str) -> list[int]:
    """Indices of `lots` in the order they should be consumed on a sell."""
    if method == "fifo":
        return list(range(len(lots)))
    if method == "lifo":
        return list(range(len(lots) - 1, -1, -1))
    if method == "hifo":
        return sorted(range(len(lots)), key=lambda i: -lots[i].cost)   # highest basis first
    raise ValueError(f"unknown lot method: {method}")


def _sell(lots: list[Lot], shares: float, price: float, date: pd.Timestamp, symbol: str,
          method: str) -> list[RealizedEvent]:
    """Consume `shares` from a name's open lots (in `method` order), emitting a realized event per
    lot touched. Lots are shrunk/removed in place; a partially-sold lot keeps its open date/basis."""
    events: list[RealizedEvent] = []
    remaining = shares
    for i in _lot_order(lots, method):
        if remaining <= 1e-12:
            break
        lot = lots[i]
        take = min(lot.shares, remaining)
        if take <= 0:
            continue
        hold = (date - lot.open_date).days
        events.append(RealizedEvent(
            date=date, symbol=symbol, shares=take, proceeds=take * price, basis=take * lot.cost,
            holding_days=hold, long_term=hold >= LONG_TERM_DAYS))
        lot.shares -= take
        remaining -= take
    lots[:] = [l for l in lots if l.shares > 1e-12]
    return events


def simulate(weights: pd.DataFrame, prices: pd.DataFrame, *, capital: float = 1_000_000.0,
             method: str = "hifo", liquidate_end: bool = False) -> SimResult:
    """Walk a LONG book (weights ≥ 0, each row summing to ≤ 1) forward through `prices`, rebalancing
    to target dollar weights each date and accounting every trade at the lot level with lot-selection
    `method`. Returns a SimResult with the realized-event ledger, the repurchase ledger (for wash-sale
    detection), and the final unrealized position. `liquidate_end=True` also realizes everything at
    the last price (to compare full-cycle tax, not just interim trims)."""
    cols = [c for c in weights.columns if c in prices.columns]
    dates = weights.index
    lots: dict[str, list[Lot]] = {c: [] for c in cols}
    shares: dict[str, float] = {c: 0.0 for c in cols}
    cash = capital
    events: list[RealizedEvent] = []
    buys: list[tuple] = []

    for dt in dates:
        px = prices.loc[dt]
        value = cash + sum(shares[c] * px[c] for c in cols if np.isfinite(px[c]))
        w = weights.loc[dt]
        for c in cols:
            p = px[c]
            if not np.isfinite(p) or p <= 0:
                continue
            target_sh = max(float(w.get(c, 0.0)), 0.0) * value / p
            delta = target_sh - shares[c]
            if delta < -1e-9:                                   # sell / trim
                sell_sh = min(-delta, shares[c])
                if sell_sh > 1e-12:
                    events.extend(_sell(lots[c], sell_sh, p, dt, c, method))
                    shares[c] -= sell_sh
                    cash += sell_sh * p
            elif delta > 1e-9:                                  # buy / add
                cash -= delta * p
                lots[c].append(Lot(open_date=dt, shares=delta, cost=p))
                shares[c] += delta
                buys.append((dt, c))

    last_px = prices.loc[dates[-1]]
    if liquidate_end:
        for c in cols:
            p = last_px[c]
            if shares[c] > 1e-12 and np.isfinite(p):
                events.extend(_sell(lots[c], shares[c], p, dates[-1], c, method))
                cash += shares[c] * p
                shares[c] = 0.0

    final = {}
    unreal = 0.0
    for c in cols:
        p = last_px[c]
        if shares[c] > 1e-12 and np.isfinite(p):
            basis = sum(l.shares * l.cost for l in lots[c])
            mv = shares[c] * p
            final[c] = (shares[c], mv, mv - basis)
            unreal += mv - basis
    return SimResult(method=method, events=events, buys=buys, final_positions=final,
                     unrealized_gain=unreal)


def flag_wash_sales(result: SimResult, window_days: int = 30) -> SimResult:
    """Mark a loss-realizing event as a wash sale (loss disallowed) if the same security is
    repurchased within `window_days` AFTER the sale — the "sell the loser and buy it back" pattern
    the rule targets. Chronology-independent post-process: the actual trades don't change, only
    whether each loss is deductible. Mutates and returns `result`.

    Simplification: the real §1091 window is ±30 days, but the symmetric *before*-window is omitted
    here because at the (date, symbol) granularity we record it cannot be told apart from the opening
    purchase of the very lot being sold (that is not a replacement). The forward window captures the
    economically dominant harvesting-abuse case without that false positive."""
    buys_by_sym: dict[str, list[pd.Timestamp]] = {}
    for d, s in result.buys:
        buys_by_sym.setdefault(s, []).append(pd.Timestamp(d))
    win = pd.Timedelta(days=window_days)
    for ev in result.events:
        if ev.gain < 0:
            for bd in buys_by_sym.get(ev.symbol, ()):
                if bd > ev.date and (bd - ev.date) <= win:
                    ev.disallowed = True
                    break
    return result


def _tax_bill(st_gain: float, lt_gain: float, st_rate: float, lt_rate: float) -> dict:
    """US-style netting: losses net within their own bucket (already summed), then a remaining net
    loss in one bucket offsets net gain in the other; only positive net gains are taxed, and any
    leftover net loss becomes a carryforward (not a refund). A documented simplification of the real
    Schedule-D ordering, but it captures the economics — deferral and LT-rate conversion."""
    st, lt = st_gain, lt_gain
    if st < 0 < lt:
        applied = min(-st, lt); lt -= applied; st += applied
    elif lt < 0 < st:
        applied = min(-lt, st); st -= applied; lt += applied
    tax = max(st, 0.0) * st_rate + max(lt, 0.0) * lt_rate
    carryforward = min(st, 0.0) + min(lt, 0.0)
    return {"tax": tax, "net_short_term": st_gain, "net_long_term": lt_gain,
            "taxable_short_term": max(st, 0.0), "taxable_long_term": max(lt, 0.0),
            "loss_carryforward": carryforward}


def tax_summary(result: SimResult, *, st_rate: float = DEFAULT_ST_RATE,
                lt_rate: float = DEFAULT_LT_RATE) -> dict:
    """Aggregate the realized ledger into a tax bill. Disallowed (wash-sale) losses are excluded from
    the deduction. Reports the short/long split, how much of realized gains landed at the favorable
    long-term rate, the wash-sale disallowance, and the deferred (still-unrealized) gain."""
    st = sum(e.gain for e in result.events if not e.long_term and not (e.disallowed and e.gain < 0))
    lt = sum(e.gain for e in result.events if e.long_term and not (e.disallowed and e.gain < 0))
    realized = sum(e.gain for e in result.events)
    lt_gains = sum(e.gain for e in result.events if e.long_term and e.gain > 0)
    all_gains = sum(e.gain for e in result.events if e.gain > 0)
    disallowed = sum(-e.gain for e in result.events if e.disallowed and e.gain < 0)
    bill = _tax_bill(st, lt, st_rate, lt_rate)
    bill.update({
        "realized_gain": realized,
        "long_term_fraction_of_gains": (lt_gains / all_gains) if all_gains > 0 else float("nan"),
        "wash_sale_disallowed": disallowed,
        "deferred_unrealized_gain": result.unrealized_gain,
        "n_events": len(result.events),
    })
    return bill


def compare_methods(weights: pd.DataFrame, prices: pd.DataFrame, *, capital: float = 1_000_000.0,
                    st_rate: float = DEFAULT_ST_RATE, lt_rate: float = DEFAULT_LT_RATE,
                    liquidate_end: bool = False) -> pd.DataFrame:
    """Run the SAME pre-tax book under HIFO (tax-aware), FIFO (naive), and LIFO and tabulate the tax
    outcome of each. The HIFO-vs-FIFO tax gap on an identical trade path is the tax alpha this layer
    captures — pure after-tax edge with no dependence on finding a significant signal."""
    rows = []
    for m in ("hifo", "fifo", "lifo"):
        res = flag_wash_sales(simulate(weights, prices, capital=capital, method=m,
                                       liquidate_end=liquidate_end))
        s = tax_summary(res, st_rate=st_rate, lt_rate=lt_rate)
        rows.append({"method": m, "tax": s["tax"], "net_short_term": s["net_short_term"],
                     "net_long_term": s["net_long_term"],
                     "lt_fraction_of_gains": s["long_term_fraction_of_gains"],
                     "wash_sale_disallowed": s["wash_sale_disallowed"],
                     "deferred_unrealized_gain": s["deferred_unrealized_gain"]})
    df = pd.DataFrame(rows).set_index("method")
    df["tax_vs_fifo"] = df["tax"] - df.loc["fifo", "tax"]        # negative = tax saved vs naive
    return df
