"""Options structuring overlay — turning the live IV surface into portfolio-level hedges & carry.

The cross-sectional book decides *what to hold*; this layer decides *how to shape the payoff* of
that book with options — the medium-term "structuring" a portfolio manager does on top of the
alpha. Three classic structures, all sized off the live Alpaca surface (options.cross_section:
atm_iv / skew_25d / dte per name) and a Black–Scholes pricer:

  * TAIL HEDGE — buy OTM puts to cap the book's left tail. The surface *times the entry*: when
    25Δ skew and IV are low, crash protection is cheap (the VRP you pay is small), so a hedge
    initiated then costs less carry for the same protection. Sized as a sleeve: cost as an
    annualized drag vs. the drawdown it removes.
  * COVERED-CALL OVERWRITE — sell OTM calls against holdings to harvest the variance risk premium
    (IV > RV on ~⅔ of names). Best on names with weak momentum (little upside given up) and high IV
    (fat premium). Income vs. the upside you cap.
  * COLLAR — finance the puts by selling the calls: a low-/zero-cost band that caps both tails,
    the standard way to de-risk a concentrated long book without paying full hedge carry.

IMPORTANT — honesty about data. Alpaca's free options feed is a LIVE snapshot only (no history and
bars are OPRA-gated), so this is a *structuring/sizing* calculator on today's surface, not a
backtested overlay. Every function is analytic and unit-tested; the P&L it reports is the
model-implied cost/benefit of the structure, clearly labelled as such — not a fabricated backtest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

TRADING_DAYS = 252


# ── Black–Scholes core ──────────────────────────────────────────────────────────────────────────
def bs_price(S: float, K: float, T: float, sigma: float, r: float = 0.04, kind: str = "put") -> float:
    """Black–Scholes European option price. T in years, sigma annualized. At/near expiry or zero vol
    it degrades gracefully to intrinsic value (max(0, payoff))."""
    if T <= 0 or sigma <= 0:
        intrinsic = (S - K) if kind == "call" else (K - S)
        return float(max(0.0, intrinsic))
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if kind == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def bs_delta(S: float, K: float, T: float, sigma: float, r: float = 0.04, kind: str = "put") -> float:
    """Option delta (call ∈ [0,1], put ∈ [−1,0])."""
    if T <= 0 or sigma <= 0:
        if kind == "call":
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1)) if kind == "call" else float(norm.cdf(d1) - 1.0)


# ── single-name structures ────────────────────────────────────────────────────────────────────
def protective_put(S: float, sigma: float, dte: float, *, moneyness: float = 0.90,
                   r: float = 0.04) -> dict:
    """Buy one OTM put at `moneyness`·S expiring in `dte` days. Returns premium (cost), its % of
    notional, the annualized carry (premium/notional × 252/dte), the strike, and the breakeven/max
    loss below which the position is protected."""
    K = moneyness * S
    T = dte / 365.0
    prem = bs_price(S, K, T, sigma, r, "put")
    return {
        "strike": K, "premium": prem, "premium_pct": prem / S,
        "annual_carry": (prem / S) * (TRADING_DAYS / max(dte, 1)),
        "protected_below": K, "max_loss_pct": (S - K) / S + prem / S,
    }


def covered_call(S: float, sigma: float, dte: float, *, moneyness: float = 1.05,
                 r: float = 0.04) -> dict:
    """Sell one OTM call at `moneyness`·S. Returns the premium collected, its % of notional, the
    annualized income yield, the strike (upside cap), and the delta given up (how much of the next
    move you forfeit above the strike).

    NB `annual_income` is the GROSS premium if the position is rolled (premium_pct·252/dte) — a
    common quote, but it is NOT free money: it compensates the capped upside / assignment risk. The
    NET expected edge from overwriting is only the variance risk premium (see `variance_premium`),
    which is far smaller. Callers should lead with the VRP, not the gross annualized premium."""
    K = moneyness * S
    T = dte / 365.0
    prem = bs_price(S, K, T, sigma, r, "call")
    return {
        "strike": K, "premium": prem, "premium_pct": prem / S,
        "annual_income": (prem / S) * (TRADING_DAYS / max(dte, 1)),
        "upside_cap_pct": (K - S) / S, "delta_given_up": bs_delta(S, K, T, sigma, r, "call"),
    }


def collar(S: float, sigma: float, dte: float, *, put_moneyness: float = 0.90,
           call_moneyness: float = 1.05, r: float = 0.04) -> dict:
    """Long put + short call around the spot: a protective band. Net cost = put premium − call
    premium (negative = a credit collar that pays you to cap upside). Reports both legs and the
    resulting downside floor / upside cap."""
    put = protective_put(S, sigma, dte, moneyness=put_moneyness, r=r)
    call = covered_call(S, sigma, dte, moneyness=call_moneyness, r=r)
    net = put["premium"] - call["premium"]
    return {
        "put_strike": put["strike"], "call_strike": call["strike"],
        "put_premium": put["premium"], "call_premium": call["premium"],
        "net_cost": net, "net_cost_pct": net / S,
        "annual_net_carry": (net / S) * (TRADING_DAYS / max(dte, 1)),
        "downside_floor_pct": -put["max_loss_pct"], "upside_cap_pct": call["upside_cap_pct"],
    }


# ── variance risk premium ───────────────────────────────────────────────────────────────────────
def variance_premium(atm_iv: float, realized_vol: float) -> dict:
    """The variance risk premium for one name: implied vs realized. Positive VRP (IV > RV) is the
    compensation for selling insurance — the edge a covered-call / vol-selling overlay harvests. Also
    returns the *variance*-space premium (σ_iv² − σ_rv²), the quantity a variance swap actually pays,
    and a coarse expected carry. The honest caveat lives with the number: this premium is paid in
    calm and clawed back violently in crashes (short-vol is short the tail)."""
    vrp_vol = atm_iv - realized_vol
    return {
        "atm_iv": atm_iv, "realized_vol": realized_vol,
        "vrp_vol": vrp_vol, "vrp_variance": atm_iv ** 2 - realized_vol ** 2,
        "sells_rich": bool(vrp_vol > 0),
    }


# ── portfolio-level structuring ─────────────────────────────────────────────────────────────────
def tail_hedge_sleeve(book_value: float, surface: pd.DataFrame, *, moneyness: float = 0.90,
                      hedge_fraction: float = 1.0, r: float = 0.04, spot: float = 100.0) -> dict:
    """Size a protective-put sleeve for a long book of `book_value`, priced off the AVERAGE surface
    (mean ATM IV and DTE across the names that have a live chain — an index-proxy hedge). `spot` is a
    nominal underlying level (the result is scale-free in S). Reports sleeve cost, annualized drag,
    and a 'timing' read: how the cost compares at the surface's current IV vs a low-IV entry.

    The point is medium-term: a hedge that costs, say, 3–5% annualized removes the deep left tail —
    whether that trade is worth it is a portfolio decision, and the surface tells you when it's cheap."""
    s = surface.dropna(subset=["atm_iv", "dte"])
    if s.empty:
        return {"ok": False, "reason": "no live surface"}
    iv = float(s["atm_iv"].mean())
    dte = float(s["dte"].median())
    unit = protective_put(spot, iv, dte, moneyness=moneyness, r=r)
    notional = book_value * hedge_fraction
    cost = unit["premium_pct"] * notional
    # A low-IV counterfactual (25th-percentile IV) — when the surface is calm the same hedge is cheaper.
    iv_low = float(s["atm_iv"].quantile(0.25))
    unit_low = protective_put(spot, iv_low, dte, moneyness=moneyness, r=r)
    return {
        "ok": True, "avg_iv": iv, "median_dte": dte, "moneyness": moneyness,
        "sleeve_notional": notional, "sleeve_cost": cost, "cost_pct": unit["premium_pct"],
        "annual_drag": unit["annual_carry"] * hedge_fraction,
        "protects_below_pct": -(unit["max_loss_pct"]),
        "cheap_entry_annual_drag": unit_low["annual_carry"] * hedge_fraction,
        "iv_percentile_note": "cost scales ~linearly with IV — initiate when IV/skew are low",
    }


def overwrite_candidates(positions: pd.Series, surface: pd.DataFrame, momentum: pd.Series, *,
                         moneyness: float = 1.05, r: float = 0.04, spot: float = 100.0,
                         momentum_quantile: float = 0.5, top_n: int | None = None) -> pd.DataFrame:
    """Rank long holdings for covered-call overwriting: prefer names with WEAK momentum (little
    expected upside to forfeit) and HIGH IV (fat premium). For each candidate, price the call and
    report the annualized income. `positions` is a per-name dollar (or weight) long exposure;
    `momentum` a per-name score (lower = weaker). Returns a per-name table sorted by income yield.

    This is the income sleeve — it monetizes the variance premium on exactly the holdings where
    capping upside costs least, the classic overlay for a long book with a modest return outlook."""
    longs = positions[positions > 0].index
    s = surface.set_index("symbol") if "symbol" in surface.columns else surface
    weak = momentum.reindex(longs)
    cutoff = weak.quantile(momentum_quantile)
    rows = []
    for sym in longs:
        if sym not in s.index or not np.isfinite(s.loc[sym, "atm_iv"]):
            continue
        if np.isfinite(weak.get(sym, np.nan)) and weak[sym] > cutoff:
            continue                                    # skip strong-momentum names (upside worth keeping)
        iv, dte = float(s.loc[sym, "atm_iv"]), float(s.loc[sym, "dte"])
        cc = covered_call(spot, iv, dte, moneyness=moneyness, r=r)
        rows.append({"symbol": sym, "notional": float(positions[sym]), "atm_iv": iv, "dte": dte,
                     "momentum": float(weak.get(sym, np.nan)), "call_strike_pct": moneyness,
                     "premium_pct": cc["premium_pct"], "annual_income": cc["annual_income"],
                     "income_dollars": cc["premium_pct"] * float(positions[sym])})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("annual_income", ascending=False).reset_index(drop=True)
    return df.head(top_n) if top_n else df
