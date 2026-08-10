"""Portfolio risk management — the analytics a desk actually runs on a live book.

Four things a risk system must answer: *how much can we lose* (VaR / expected shortfall), *where is the
risk* (marginal risk contributions), *what happens in a crisis* (stress / scenario replay), and *are we
inside our mandate* (limit checks). All operate on a strategy's realized net series and/or its held
weights + a covariance — so they drop straight onto any `engine.StrategyResult`.

Complements `riskmodel.py` (the factor risk model + optimizer used to *build* portfolios); this module
*monitors* a portfolio once it exists. Pure NumPy/pandas — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats as sstats

TRADING_DAYS = 252


# ── Loss measures ─────────────────────────────────────────────────────────────────────────────────
def value_at_risk(returns, alpha: float = 0.95, method: str = "historical") -> float:
    """Daily Value-at-Risk at confidence `alpha`, returned as a POSITIVE loss fraction (0.02 = a 2% day).
    `historical` = empirical quantile; `gaussian` = μ+zσ; `cornish_fisher` = Gaussian corrected for the
    return distribution's skew and fat tails (the honest choice — financial returns are not normal)."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 8:
        return 0.0
    if method == "historical":
        return float(-np.percentile(r, (1 - alpha) * 100))
    mu, sd = float(r.mean()), float(r.std())
    z = float(sstats.norm.ppf(1 - alpha))                 # negative left-tail quantile
    if method == "cornish_fisher":
        s, k = float(sstats.skew(r)), float(sstats.kurtosis(r, fisher=True))   # excess kurtosis
        z = z + (z**2 - 1) * s / 6 + (z**3 - 3 * z) * k / 24 - (2 * z**3 - 5 * z) * s**2 / 36
    return float(-(mu + z * sd))


def expected_shortfall(returns, alpha: float = 0.95) -> float:
    """Expected shortfall / CVaR — the average loss *given* a worse-than-VaR day. A positive loss
    fraction. Coherent where VaR isn't, and it sees the tail VaR ignores."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 8:
        return 0.0
    cutoff = np.percentile(r, (1 - alpha) * 100)
    tail = r[r <= cutoff]
    return float(-tail.mean()) if len(tail) else float(-cutoff)


# ── Where the risk is ─────────────────────────────────────────────────────────────────────────────
def marginal_risk_contributions(weights, cov) -> np.ndarray:
    """Each position's contribution to portfolio volatility (they SUM to the portfolio vol). Two books
    with the same vol can hide very different concentration — this is what says which bets own the risk."""
    w = np.asarray(weights, dtype=float)
    cov = np.asarray(cov, dtype=float)
    port_vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
    if port_vol <= 0:
        return np.zeros_like(w)
    return w * (cov @ w) / port_vol


def risk_report(net: pd.Series, weights: pd.Series | None = None, cov: np.ndarray | None = None,
                sleeves: dict | None = None) -> dict:
    """A one-call risk snapshot: realized vol, historical & Cornish-Fisher VaR, expected shortfall, and —
    if given a current weight vector + covariance — the ex-ante annual vol and the risk contribution by
    sleeve (where the risk lives right now)."""
    r = net.to_numpy(dtype=float)
    out = {
        "ann_vol": round(float(np.nanstd(r) * np.sqrt(TRADING_DAYS)), 4),
        "var_95_hist": round(value_at_risk(r, 0.95, "historical"), 5),
        "var_99_hist": round(value_at_risk(r, 0.99, "historical"), 5),
        "var_95_cornish_fisher": round(value_at_risk(r, 0.95, "cornish_fisher"), 5),
        "cvar_95": round(expected_shortfall(r, 0.95), 5),
    }
    if weights is not None and cov is not None:
        w = weights.to_numpy(dtype=float)
        out["exante_ann_vol"] = round(float(np.sqrt(max(w @ cov @ w, 0.0)) * np.sqrt(TRADING_DAYS)), 4)
        mctr = pd.Series(marginal_risk_contributions(w, cov), index=weights.index)
        total = mctr.sum()
        frac = (mctr / total) if total != 0 else mctr
        if sleeves:
            frac = frac.groupby(lambda a: sleeves.get(a, "Other")).sum()
        out["risk_contribution"] = frac.sort_values(ascending=False).round(3).to_dict()
    return out


# ── Stress / scenario replay ──────────────────────────────────────────────────────────────────────
def stress_test(weights: pd.Series, prices: pd.DataFrame,
                scenarios: list[tuple[str, str, str]]) -> list[dict]:
    """Replay historical stress windows through a FIXED book: apply today's weights to each scenario's
    realized asset returns → the P&L the current portfolio would have taken. 'What would this book have
    lost in <crisis>?' — the question regular performance stats never ask of the *current* positioning."""
    w = weights.reindex(prices.columns).fillna(0.0).to_numpy(dtype=float)
    rets = prices.pct_change()
    out = []
    for name, start, end in scenarios:
        seg = rets.loc[start:end].dropna()
        if len(seg) == 0:
            continue
        book = seg.to_numpy() @ w
        out.append({"scenario": name, "start": start, "end": end, "n_days": len(seg),
                    "book_return": round(float(np.prod(1 + book) - 1), 4),
                    "worst_day": round(float(book.min()), 4)})
    return out


# ── Limits (the mandate) ──────────────────────────────────────────────────────────────────────────
@dataclass
class RiskLimits:
    """A book's mandate. Realistic defaults for a diversified multi-asset long/short book."""
    max_gross: float = 2.5           # gross leverage
    max_name_weight: float = 0.60    # single-position |weight|
    max_sleeve_weight: float = 0.90  # net sleeve concentration
    max_ann_vol: float = 0.25        # realized annual vol
    max_var_95: float = 0.05         # daily 95% VaR


def check_limits(weights: pd.DataFrame, net: pd.Series, limits: RiskLimits,
                 sleeves: dict | None = None) -> list[dict]:
    """Check a book against its mandate — the gate a desk runs before (and while) a strategy is live.
    Returns every check with its value, cap, and pass/breach, worst offenders first."""
    gross = weights.abs().sum(axis=1)
    name = weights.abs().max().max()
    checks = [
        {"limit": "max_gross", "value": float(gross.max()), "cap": limits.max_gross},
        {"limit": "max_name_weight", "value": float(name), "cap": limits.max_name_weight},
        {"limit": "max_ann_vol", "value": round(float(net.std() * np.sqrt(TRADING_DAYS)), 4), "cap": limits.max_ann_vol},
        {"limit": "max_var_95", "value": round(value_at_risk(net.to_numpy(), 0.95, "historical"), 5), "cap": limits.max_var_95},
    ]
    if sleeves:
        grp = [sleeves.get(a, "Other") for a in weights.columns]
        sleeve_net = weights.T.groupby(grp).sum().T.abs().max().max()   # net weight per sleeve, over time
        checks.append({"limit": "max_sleeve_weight", "value": float(sleeve_net), "cap": limits.max_sleeve_weight})
    for c in checks:
        c["breached"] = bool(c["value"] > c["cap"])
    return sorted(checks, key=lambda c: c["value"] / c["cap"], reverse=True)
