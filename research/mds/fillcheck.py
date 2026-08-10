"""Fill validation — modeled cost vs. *measured* cost against real Alpaca paper fills.

The whole platform's execution layer is *modeled* (Corwin–Schultz / ADV-tier spread, square-root impact).
The honest question a desk asks is: *what did the real fill actually cost?* This module measures it —
against real quotes and real paper-trade fills — and calibrates the model to reality. It's the difference
between "my backtest assumed 5 bps" and "I submitted the order and it cost 3.1 bps, so my model was 1.6×
conservative."

Pure analytics (network-free, unit-tested); `run_paper.py` supplies the live quotes and paper fills.
"""

from __future__ import annotations

import numpy as np


def realized_spread(bid: float, ask: float) -> float:
    """The real quoted proportional spread (ask − bid) / mid — what a marketable order pays to cross."""
    mid = (bid + ask) / 2.0
    return (ask - bid) / mid if mid > 0 else 0.0


def implementation_shortfall(fill_price: float, decision_mid: float, side: str) -> float:
    """Perold implementation shortfall for one fill, as a positive-is-cost fraction: how far the fill
    printed from the mid at the moment you decided to trade. Buys pay up (fill > mid), sells give up
    (fill < mid)."""
    if decision_mid <= 0:
        return 0.0
    signed = (fill_price - decision_mid) if side == "buy" else (decision_mid - fill_price)
    return signed / decision_mid


def roundtrip_cost(buy_fill: float, buy_mid: float, sell_fill: float, sell_mid: float) -> float:
    """Effective spread paid on a buy→sell round trip as a taker = the two implementation shortfalls
    summed. Comparable to one full quoted spread (you cross to the ask, then to the bid)."""
    return (implementation_shortfall(buy_fill, buy_mid, "buy")
            + implementation_shortfall(sell_fill, sell_mid, "sell"))


def calibration(realized: float, modeled: float) -> float:
    """Model calibration factor = realized / modeled. >1 ⇒ the model UNDER-charged (optimistic); <1 ⇒ it
    was conservative. The number you'd multiply the model by to match reality."""
    return realized / modeled if modeled > 0 else float("nan")


def summarize(rows: list[dict]) -> dict:
    """Aggregate a set of per-symbol validation rows (each with realized & modeled spread, in bps)."""
    real = np.array([r["realized_bps"] for r in rows if np.isfinite(r.get("realized_bps", np.nan))])
    modeled = np.array([r["modeled_bps"] for r in rows if np.isfinite(r.get("modeled_bps", np.nan))])
    if len(real) == 0 or len(modeled) == 0:
        return {"n": 0}
    return {"n": len(real), "mean_realized_bps": round(float(real.mean()), 2),
            "mean_modeled_bps": round(float(modeled.mean()), 2),
            "calibration": round(float(real.mean() / modeled.mean()), 2) if modeled.mean() > 0 else float("nan")}
