"""Capacity & crowding — the trader's game-theoretic sizing layer.

A backtest reports a signal's Sharpe at *infinitesimal* size. The trader's real question is
different: how much capital can this alpha absorb before its own market impact — and everyone
else chasing it — eats the edge? Two effects, both modelled here:

  * Impact / capacity (own size). Deploying capital C into a signal moves the market against you.
    With a linear-impact (Kyle-λ) model the realised return RATE falls linearly with size,
        rate(C) = μ − λ·C,
    so total profit  P(C) = μ·C − λ·C²  is CONCAVE, maximised at the capacity  C* = μ/(2λ).
    Past C* you are paying more impact than the alpha is worth. This is why the profit-maximising
    allocation is NOT "all-in on the highest Sharpe" — it is water-filling across signals so each
    stays near its own capacity.

  * Crowding (others' size). When K players share a signal, their capital erodes the alpha every-
    one sees (rate −= γ·(others' capital)). The symmetric Nash equilibrium over-deploys relative
    to a single owner — a tragedy of the commons: aggregate profit FALLS as the crowd grows even
    though total capital rises. That is the quant-research reality behind "this factor is crowded."

The point of the layer is judgment about SIZE and COMPETITION, which a naive optimizer ignores.
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def net_rate(mu, lam, capital):
    """Realised per-unit-capital return rate after own market impact: μ − λ·C."""
    return np.asarray(mu, float) - np.asarray(lam, float) * np.asarray(capital, float)


def total_profit(mu, lam, capital):
    """Total profit deploying `capital` into each signal: Σ (μ_i·C_i − λ_i·C_i²)."""
    mu, lam, C = (np.asarray(x, float) for x in (mu, lam, capital))
    return float(np.sum(mu * C - lam * C ** 2))


def optimal_capacity(mu, lam):
    """Single-signal profit-maximising capital C* = μ/(2λ) — the 'capacity' of the alpha."""
    return np.asarray(mu, float) / (2.0 * np.asarray(lam, float))


def allocate_with_capacity(mu, lam, budget: float):
    """Split a fixed capital `budget` across signals to maximise total impact-aware profit
        max Σ (μ_i·C_i − λ_i·C_i²)   s.t.  Σ C_i = budget,  C_i ≥ 0.
    KKT gives water-filling: C_i = max(0, (μ_i − ν)/(2λ_i)) with ν set so the split sums to
    budget. High-impact (low-capacity) signals get less capital even at equal μ — the whole point.
    """
    mu = np.asarray(mu, float)
    lam = np.asarray(lam, float)
    lo = float(mu.min()) - 2.0 * float(lam.max()) * budget - 1.0  # ν low enough → C sums high
    hi = float(mu.max())                                          # ν = max μ → all C = 0
    for _ in range(200):
        nu = 0.5 * (lo + hi)
        C = np.clip((mu - nu) / (2.0 * lam), 0.0, None)
        if C.sum() > budget:
            lo = nu   # too much capital deployed → raise the shadow price ν
        else:
            hi = nu
    return np.clip((mu - hi) / (2.0 * lam), 0.0, None)


def concentrate(mu, budget: float):
    """The naive comparison: dump the whole budget into the highest-μ signal."""
    mu = np.asarray(mu, float)
    C = np.zeros_like(mu)
    C[int(np.argmax(mu))] = budget
    return C


def crowding_equilibrium(mu: float, lam: float, n_players: int) -> dict:
    """Symmetric Cournot–Nash equilibrium for K identical players sharing one signal. They all
    trade against the SAME order book, so the realised rate depends on total deployed capital X:
    rate = μ − λ·X. Each player maximises  C_i·(μ − λ·(C_i + Σ_{j≠i} C_j)); the symmetric solution
    is  C* = μ / (λ·(K+1)),  giving common rate  μ/(K+1)  and aggregate profit  K·μ²/(λ·(K+1)²).

    K=1 reproduces the single-owner capacity C*=μ/2λ, profit μ²/4λ. As K grows, total capital
    rises toward μ/λ, the per-name rate collapses toward 0, and AGGREGATE profit falls from the
    monopoly optimum — the tragedy of the commons that makes a crowded factor un-investable."""
    k = int(n_players)
    c = mu / (lam * (k + 1))
    total = k * c
    rate = mu - lam * total                 # common post-impact rate everyone earns
    per_player_profit = c * rate
    return {
        "n_players": k,
        "capital_each": c,
        "total_capital": total,
        "rate": rate,
        "profit_each": per_player_profit,
        "aggregate_profit": k * per_player_profit,
    }


def sharpe_at_capacity(mu, lam, sigma, capital) -> float:
    """Annualised Sharpe of a deployed book: net rate / vol. σ is the per-unit-capital return
    vol (impact hits the mean, not the noise). Assumes daily μ/σ inputs."""
    rate = net_rate(mu, lam, capital)
    s = float(np.asarray(sigma, float).mean())
    return float(np.mean(rate) / s * np.sqrt(TRADING_DAYS)) if s > 0 else 0.0
