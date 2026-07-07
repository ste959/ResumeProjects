"""Passive (maker) execution study — does a signal that dies as a TAKER survive as a MAKER?

The taker backtest crosses the spread on every trade, so a sub-spread edge is eaten by cost and
"dies after spread". But that is only half the question. A **maker** posts passively and *earns*
the half-spread on each fill — at the cost of **adverse selection**: a resting bid fills precisely
when the market is trading down to it (you buy right before further declines). The net maker edge is

    net per fill  =  half-spread earned  −  fee  +  side · markout

where the markout (signed forward mid move after the fill) is negative in expectation — that IS the
adverse selection. If the half-spread beats it, the maker survives where the taker didn't; if not,
the signal is untradable on both sides. This decomposition — spread vs adverse selection — is the
whole point, and it is the honest answer to the question the taker verdict only *names*.

Simplifications (flagged): fills are modelled as "price crossed my quote" with no queue-position
gating, so fill *counts* are optimistic — but the **per-fill economics** below (the headline) are
unaffected by that, since queue position scales spread and markout together.
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def markout_bps(mid, horizon: int) -> np.ndarray:
    """Signed forward mid move `horizon` samples ahead, in bps (the adverse-selection measure)."""
    m = np.asarray(mid, dtype=float)
    out = np.full(len(m), np.nan)
    if horizon < len(m):
        out[:-horizon] = (m[horizon:] / m[:-horizon] - 1.0) * 1e4
    return out


def maker_backtest(mid, spread_bps, inv_cap: int = 10, maker_fee_bps: float = 0.0,
                   markout_h: int = 100) -> dict:
    """Inventory-capped two-sided passive market maker over a reconstructed mid/spread path.

    A resting bid fills when the next mid ticks down to it, an offer when the next mid ticks up — so
    fills are adversely selected by construction, which is exactly the effect being measured. The
    inventory cap makes quoting mean-revert (buy dips, sell rips), keeping the book bounded. Returns
    aggregate per-fill economics AND the per-fill detail (index, side, net) so a signal can be tested
    as a fill FILTER afterwards (see `signal_split`)."""
    mid = np.asarray(mid, dtype=float)
    sp = np.asarray(spread_bps, dtype=float)
    n = len(mid)

    q = 0
    fill_idx: list[int] = []
    fill_side: list[int] = []
    for i in range(n - 1):
        if sp[i] <= 0:                                    # never quote into a crossed/locked-through book
            continue
        hs = mid[i] * sp[i] / 2.0 / 1e4
        nxt = mid[i + 1]
        if nxt <= mid[i] - hs and q < inv_cap:          # our bid gets hit (price ticked down)
            q += 1
            fill_idx.append(i)
            fill_side.append(+1)
        elif nxt >= mid[i] + hs and q > -inv_cap:       # our offer gets lifted (price ticked up)
            q -= 1
            fill_idx.append(i)
            fill_side.append(-1)

    if not fill_idx:
        return {"n_fills": 0, "spread_bps": 0.0, "adverse_bps": 0.0, "net_bps": 0.0,
                "fee_bps": maker_fee_bps, "idx": np.array([], int), "side": np.array([], int),
                "net": np.array([])}

    idx = np.array(fill_idx)
    side = np.array(fill_side)
    mo = markout_bps(mid, markout_h)
    valid = np.isfinite(mo[idx])
    idx, side = idx[valid], side[valid]
    half_spread = sp[idx] / 2.0                          # bps earned by posting inside the touch
    signed_markout = side * mo[idx]                      # + favourable, − adverse (adverse in expectation)
    net = half_spread - maker_fee_bps + signed_markout
    return {
        "n_fills": int(len(idx)),
        "spread_bps": float(half_spread.mean()),        # + earned
        "adverse_bps": float(signed_markout.mean()),    # − adverse selection
        "net_bps": float(net.mean()),                   # spread − adverse − fee
        "fee_bps": maker_fee_bps,
        "idx": idx, "side": side, "net": net,           # per-fill detail for signal conditioning
    }


def signal_split(res: dict, signal) -> dict:
    """Does the signal predict which fills to KEEP? Split the two-sided maker's fills by whether the
    signal AGREED with the fill direction (sign(signal)==side) and compare net per fill. If the
    signal has maker value it should improve the aligned subset's net (it avoids adverse selection);
    a signal with no maker value leaves both subsets the same. This is the clean test — it doesn't
    entangle the answer with inventory management the way one-sided quoting would."""
    if res["n_fills"] == 0:
        return {"aligned_net_bps": 0.0, "contra_net_bps": 0.0, "aligned_fills": 0, "contra_fills": 0}
    sig = np.asarray(signal, dtype=float)[res["idx"]]
    # Only fills the model actually SCORED are eligible: drop unpredicted (NaN, e.g. walk-forward
    # warm-up) and zero-sign fills from BOTH buckets — dumping them into "contra" would contaminate
    # it and understate the signal's discrimination.
    scored = np.isfinite(sig) & (sig != 0)
    s = np.sign(sig[scored])
    side, net = res["side"][scored], res["net"][scored]
    a, c = net[s == side], net[s != side]
    return {
        "aligned_net_bps": float(a.mean()) if len(a) else float("nan"),
        "contra_net_bps": float(c.mean()) if len(c) else float("nan"),
        "aligned_fills": int(len(a)), "contra_fills": int(len(c)),
    }
