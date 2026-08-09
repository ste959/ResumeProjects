"""Factor risk model + constrained mean-variance optimizer — the portfolio-construction core.

A signal gives you *expected returns* (alpha). Turning alpha into a book needs the other half:
a *risk model* (how do names co-move, so a bet isn't secretly a concentrated factor punt?) and an
*optimizer* (maximize alpha per unit risk subject to real constraints — neutrality, position caps,
turnover). This module is a compact Barra-style build of both.

RISK MODEL (structural, not a raw sample covariance).  A raw 123×123 sample covariance on ~1500
days is noisy and near-singular; every practitioner instead imposes structure:

        r_i,t = Σ_k B_i,k · f_k,t + u_i,t          (each name = factor exposures × factor returns + idio)
        Σ     = B · F · Bᵀ + diag(d)               (asset covariance from factors + specific risk)

with factors = market beta + GICS sector dummies + the style scores (the family scores from
factors.py). Factor returns f are recovered by a cross-sectional regression of realized returns on
the (lagged, causal) exposures each day; F is their EWMA covariance and d the EWMA specific
variance. This collapses ~7,600 free covariance entries to a handful of factors + a diagonal — the
whole reason factor risk models exist.

OPTIMIZER (analytic, constrained).  Maximize αᵀw − ½λ·wᵀΣw subject to a set of linear EQUALITY
constraints C·w = 0 (dollar-neutral, and factor-neutral to beta/sectors). The KKT solution is
closed-form — a constrained "characteristic portfolio" — so no solver dependency is needed:

        w* ∝ Σ⁻¹ (α − Cᵀ(CΣ⁻¹Cᵀ)⁻¹ CΣ⁻¹ α),   then scaled to the gross target.

The Σ⁻¹ is what makes this more than a z-score book: it down-weights alpha in high-covariance
directions (don't take the same bet twice) and shapes the trade to the risk model. Box (position-
cap) constraints and a turnover budget are applied as documented post-steps (clip + renormalize;
partial-rebalance toward the target) — an honest, transparent approximation to a full QP, not a
silent one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# EWMA covariance / variance of factor returns
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def _ewma_weights(n: int, halflife: float) -> np.ndarray:
    """Normalized exponential weights, most recent last (weight ∝ 0.5^(age/halflife))."""
    if halflife <= 0:
        w = np.ones(n)
    else:
        age = np.arange(n)[::-1]                      # 0 for the last row (most recent)
        w = 0.5 ** (age / halflife)
    return w / w.sum()


def ewma_cov(returns: np.ndarray, halflife: float = 63.0) -> np.ndarray:
    """EWMA covariance of a (T × K) factor-return matrix. Recent observations weigh more (risk is
    persistent and regime-dependent, so a flat sample cov over 6 years is stale). Mean-subtracted
    with the same weights."""
    R = np.atleast_2d(np.asarray(returns, dtype=float))
    T, k = R.shape
    if T < 2:                                       # can't estimate covariance from <2 rows
        return np.eye(k) * 1e-8                      # tiny PD floor rather than a NaN matrix (1 - Σw² = 0)
    w = _ewma_weights(T, halflife)
    denom = 1.0 - np.sum(w ** 2)                     # reliability-weighted normalization
    if denom <= 1e-12:                              # weights too concentrated to normalize — fall back
        return np.diag(np.var(R, axis=0)) + np.eye(k) * 1e-12
    mu = w @ R
    dev = R - mu
    return (dev * w[:, None]).T @ dev / denom


def ewma_var(residuals: np.ndarray, halflife: float = 63.0, floor: float = 1e-8) -> np.ndarray:
    """Per-column EWMA variance of a (T × M) residual matrix — the specific (idiosyncratic) risk of
    each name. NaNs (a name absent that day) are ignored per column; a variance floor keeps a name
    with a short history from getting an over-confident near-zero specific risk."""
    R = np.asarray(residuals, dtype=float)
    T, M = R.shape
    out = np.full(M, floor)
    for j in range(M):
        col = R[:, j]
        m = np.isfinite(col)
        if m.sum() < 5:
            continue
        c = col[m]
        w = _ewma_weights(len(c), halflife)
        mu = w @ c
        out[j] = max(float(w @ (c - mu) ** 2 / (1.0 - np.sum(w ** 2))), floor)
    return out


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Exposure assembly + cross-sectional factor returns
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def build_exposures(date, beta: pd.DataFrame, sectors: dict, style_scores: dict[str, pd.DataFrame],
                    names: list[str]) -> tuple[np.ndarray, list[str]]:
    """Assemble the exposure matrix B (M names × K factors) for one date, using only info known by
    then: [market beta] + [GICS sector dummies] + [style scores]. Returns (B, factor_labels).

    Beta and style scores are read at `date` (both are already causal — beta is a trailing window,
    style scores consume only past returns/filings). Sector dummies are static membership. NaN
    exposures are filled with the cross-sectional mean so a name is never dropped for one missing
    style; a name missing beta gets beta 1 (market-like) as a neutral prior."""
    M = len(names)
    b = beta.loc[date].reindex(names) if date in beta.index else pd.Series(np.nan, index=names)
    b = b.fillna(1.0).to_numpy(dtype=float)
    cols = [b - b.mean()]                                        # beta as a centred factor
    labels = ["beta"]

    sec = pd.Series(sectors).reindex(names)
    for s in sorted(sec.dropna().unique()):
        cols.append((sec == s).to_numpy(dtype=float))
        labels.append(f"sector:{s}")

    for style, frame in style_scores.items():
        v = frame.loc[date].reindex(names) if date in frame.index else pd.Series(np.nan, index=names)
        v = v.fillna(0.0).to_numpy(dtype=float)                 # 0 = neutral on a missing style
        cols.append(v)
        labels.append(f"style:{style}")

    B = np.column_stack(cols)
    return B, labels


def cross_sectional_factor_returns(rets: pd.DataFrame, beta: pd.DataFrame, sectors: dict,
                                   style_scores: dict[str, pd.DataFrame], dates
                                   ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Recover factor returns by regressing each day's realized cross-section of returns on the
    exposures known the day before (r_t ~ B_{t−1}). Returns (factor_returns T×K, residuals T×M,
    label info). This is the estimation half of the risk model — F comes from the covariance of the
    factor-return series, d from the residuals — and, as a by-product, the factor returns are exactly
    the long/short factor-mimicking portfolios.

    Causal by construction: exposures are lagged one day relative to the return being explained, so
    nothing here peeks at contemporaneous information."""
    names = list(rets.columns)
    f_rows, u_rows, f_index, labels_ref = [], [], [], None
    prev = None
    for dt in dates:
        r = rets.loc[dt].reindex(names)
        if prev is not None:
            B, labels = build_exposures(prev, beta, sectors, style_scores, names)
            valid = r.notna().to_numpy()
            if valid.sum() > B.shape[1] + 2:
                Bv, rv = B[valid], r.to_numpy(dtype=float)[valid]
                coef, *_ = np.linalg.lstsq(Bv, rv, rcond=None)
                resid = np.full(len(names), np.nan)
                resid[valid] = rv - Bv @ coef
                f_rows.append(coef)
                u_rows.append(resid)
                f_index.append(dt)
                labels_ref = labels
        prev = dt
    if not f_rows:
        empty = pd.DataFrame(index=[], columns=names)
        return pd.DataFrame(), empty, {"labels": []}
    fr = pd.DataFrame(f_rows, index=pd.DatetimeIndex(f_index), columns=labels_ref)
    ur = pd.DataFrame(u_rows, index=pd.DatetimeIndex(f_index), columns=names)
    return fr, ur, {"labels": labels_ref, "names": names}


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Asset covariance
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def asset_covariance(B: np.ndarray, F: np.ndarray, d: np.ndarray, ridge: float = 1e-10) -> np.ndarray:
    """Σ = B F Bᵀ + diag(d) — the structured asset covariance. A tiny ridge on the diagonal keeps it
    strictly positive-definite (hence invertible) even if a factor is redundant or a name has a
    near-zero specific variance."""
    Sigma = B @ F @ B.T + np.diag(d)
    return Sigma + ridge * np.eye(Sigma.shape[0])


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Constrained mean-variance optimizer
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def optimize(alpha: np.ndarray, Sigma: np.ndarray, C: np.ndarray | None = None, *,
             gross: float = 1.0, position_cap: float | None = None, w_prev: np.ndarray | None = None,
             max_turnover: float | None = None) -> np.ndarray:
    """Constrained mean-variance weights (see module docstring for the KKT derivation).

    max_w  αᵀw − ½·wᵀΣw   s.t.  C·w = 0   →   w ∝ Σ⁻¹(α − Cᵀ(CΣ⁻¹Cᵀ)⁻¹CΣ⁻¹α), scaled to `gross`.

    `C` rows are the equality constraints (each a linear exposure forced to 0): pass Bᵀ-rows for the
    factors you want neutralized plus a row of ones for dollar-neutrality. `position_cap` clips |w_i|
    and renormalizes (dollar-neutral + gross) — a transparent box projection. `max_turnover`, with
    `w_prev`, partial-rebalances toward the target (w = w_prev + κ·Δ) so trading never exceeds the
    budget — the standard, honest way to respect turnover without a full QP."""
    alpha = np.asarray(alpha, dtype=float)
    n = len(alpha)
    Sinv = np.linalg.inv(Sigma)
    Sinv_a = Sinv @ alpha
    if C is not None and len(C):
        C = np.atleast_2d(C)
        CSinv = C @ Sinv
        M = CSinv @ C.T
        # lstsq (not solve) so redundant/collinear constraints — e.g. the dollar-neutral row equals
        # the sum of the sector rows — don't make M singular; the Σ⁻¹-metric projection onto null(C)
        # is well-defined regardless, and the min-norm ν it returns gives exactly that projection.
        nu, *_ = np.linalg.lstsq(M, CSinv @ alpha, rcond=None)
        w = Sinv_a - Sinv @ (C.T @ nu)                  # project alpha onto the constraint null space
    else:
        w = Sinv_a

    w = _scale_gross(w, gross)
    if position_cap is not None:
        for _ in range(64):                              # clip/renormalize passes; converges quickly
            capped = np.clip(w, -position_cap, position_cap)
            capped = capped - capped.mean()              # restore dollar-neutrality
            capped = _scale_gross(capped, gross)
            if np.max(np.abs(capped)) <= position_cap + 1e-9:
                w = capped
                break
            w = capped
        else:
            w = np.clip(w, -position_cap, position_cap)  # guarantee the cap even if gross drifts a touch
    if max_turnover is not None and w_prev is not None:
        w = _apply_turnover_budget(w, np.asarray(w_prev, dtype=float), max_turnover)
    return w


def _scale_gross(w: np.ndarray, gross: float) -> np.ndarray:
    g = np.abs(w).sum()
    return w * (gross / g) if g > 0 else w


def _apply_turnover_budget(w_target: np.ndarray, w_prev: np.ndarray, max_turnover: float) -> np.ndarray:
    """Partial-rebalance from w_prev toward w_target so Σ|Δw| ≤ max_turnover. If the full trade is
    within budget, take it; otherwise scale the trade vector by κ = budget/required. Trading a
    fraction of the way to the target is the practitioner's turnover control — it keeps the book on
    the alpha's side while capping the cost drag."""
    delta = w_target - w_prev
    required = np.abs(delta).sum()
    if required <= max_turnover or required == 0:
        return w_target
    return w_prev + (max_turnover / required) * delta


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# High-level: fit a risk model on a trailing window and emit an optimized book, walk-forward
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def fit_risk_model(rets: pd.DataFrame, beta: pd.DataFrame, sectors: dict,
                   style_scores: dict[str, pd.DataFrame], window_dates, *,
                   cov_halflife: float = 63.0) -> dict:
    """Fit F (factor covariance) and d (specific variance) over a trailing set of dates. Returns a
    dict with F, d, factor labels and the name order — everything `asset_covariance` needs at the
    rebalance date."""
    fr, ur, info = cross_sectional_factor_returns(rets, beta, sectors, style_scores, window_dates)
    if fr.empty:
        return {"ok": False}
    F = ewma_cov(fr.to_numpy(), cov_halflife)
    d = ewma_var(ur.to_numpy(), cov_halflife)
    return {"ok": True, "F": F, "d": d, "labels": info["labels"], "names": info["names"],
            "factor_returns": fr, "residuals": ur}


def optimized_weights(alpha_score: pd.DataFrame, rets: pd.DataFrame, beta: pd.DataFrame,
                      sectors: dict, style_scores: dict[str, pd.DataFrame], *,
                      lookback: int = 252, rebalance: int = 21, gross: float = 1.0,
                      position_cap: float = 0.05, max_turnover: float | None = 0.20,
                      neutralize_styles: bool = False) -> pd.DataFrame:
    """Walk-forward optimized book: every `rebalance` days, refit the risk model on the trailing
    `lookback` days of factor returns, build Σ at the rebalance date, and solve the constrained MVO
    for that day's alpha (held until the next rebalance). Neutralizes beta and sectors by default;
    optionally the styles too. No look-ahead — the covariance and exposures at a rebalance date use
    only prior data.

    Efficiency: the per-day cross-sectional factor regressions are computed ONCE over the whole
    sample; each rebalance then just re-estimates F and d from the trailing slice of that series
    (instead of re-regressing the window every time). Returns a dates × symbols weight frame
    (dollar-neutral, gross ≈ `gross`)."""
    names = list(rets.columns)
    dates = rets.index
    fr, ur, _ = cross_sectional_factor_returns(rets, beta, sectors, style_scores, dates)
    weights = pd.DataFrame(0.0, index=dates, columns=names)
    if fr.empty:
        return weights
    w_prev = None
    i = lookback
    while i < len(dates):
        rebal_date = dates[i]
        asof = dates[i - 1]
        win_f = fr.loc[fr.index <= asof].tail(lookback)       # trailing factor returns (causal)
        win_u = ur.loc[ur.index <= asof].tail(lookback)
        if len(win_f) >= 20:
            F = ewma_cov(win_f.to_numpy())
            d = ewma_var(win_u.to_numpy())
            B, labels = build_exposures(asof, beta, sectors, style_scores, names)
            Sigma = asset_covariance(B, F, d)
            a = alpha_score.loc[rebal_date].reindex(names).fillna(0.0).to_numpy(dtype=float)
            # Constraint rows: dollar-neutral + every beta/sector (and optionally style) exposure = 0.
            keep = [k for k, lab in enumerate(labels)
                    if lab == "beta" or lab.startswith("sector:")
                    or (neutralize_styles and lab.startswith("style:"))]
            C = np.vstack([np.ones(len(names)), B[:, keep].T])
            w = optimize(a, Sigma, C, gross=gross, position_cap=position_cap,
                         w_prev=w_prev, max_turnover=max_turnover)
            block = dates[i:i + rebalance]
            weights.loc[block] = np.tile(w, (len(block), 1))
            w_prev = w
        i += rebalance
    return weights
