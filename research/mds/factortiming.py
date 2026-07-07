"""Regime-conditional factor allocation — timing the factor MIX with the macro state.

Which factor pays is regime-dependent: momentum and value are cyclical (they lead in trending,
risk-on markets and crash in reversals), while quality and low-risk are defensive (they earn their
keep when credit and vol blow out). A static equal-weight composite ignores this; a *factor-timing*
overlay tilts the family weights with an EXOGENOUS regime read — here the causal FRED credit/VIX
risk-appetite score already built in `macro.risk_off_state` (score∈[0,1], 1 = full risk-on, shifted
one day so it never peeks).

Two distinct levers, kept separate on purpose:

  1. MIX timing (`timed_composite`) — rotate *within* the book: in risk-off, shift the family blend
     toward defensive families (quality, low-risk) and away from cyclical ones (value, momentum,
     reversal, flow). This changes *what* you hold, not how much. It is dollar-neutral throughout,
     so it is a genuine cross-sectional bet, not a beta timing trick.

  2. EXPOSURE timing (`apply_regime_exposure`) + risk budgeting (`risk_budget`) — scale *how much*
     of the (directional) book is on, cutting gross in risk-off and vol-targeting the whole path.
     This is the drawdown-control half; it re-times exposure and cannot create cross-sectional alpha.

Factor timing is notoriously fragile out-of-sample (Asness's "factor timing is deceptively
difficult"), and ~6 years is only a couple of macro cycles — so the honest test in run_portfolio
compares timed vs static and reports whichever wins, rather than assuming the tilt helps.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import factors as fac
from . import portfolio as pf

# Family tilts at the two regime extremes (weights need not sum to 1 — the blend renormalizes to the
# families actually present each day). Risk-ON leans cyclical; risk-OFF leans defensive. The neutral
# (score 0.5) point is close to equal-weight, so with no regime signal this ≈ the static composite.
RISK_ON_TILT: dict[str, float] = {
    "value": 1.3, "momentum": 1.3, "reversal": 1.0, "quality": 0.8, "low_risk": 0.6, "flow": 1.1,
}
RISK_OFF_TILT: dict[str, float] = {
    "value": 0.7, "momentum": 0.5, "reversal": 1.0, "quality": 1.3, "low_risk": 1.6, "flow": 0.9,
}


def regime_family_weights(risk_score: pd.Series, families: list[str], *,
                          on_tilt: dict[str, float] = RISK_ON_TILT,
                          off_tilt: dict[str, float] = RISK_OFF_TILT) -> pd.DataFrame:
    """Per-day family weights (dates × families) interpolated between the risk-off and risk-on tilts
    by the risk-appetite score: w_fam(t) = off + score(t)·(on − off). A missing score (warm-up) maps
    to the neutral midpoint. Only the requested `families` are returned."""
    s = risk_score.clip(0.0, 1.0).fillna(0.5)
    out = {}
    for fam in families:
        on = on_tilt.get(fam, 1.0)
        off = off_tilt.get(fam, 1.0)
        out[fam] = off + s * (on - off)
    return pd.DataFrame(out, index=risk_score.index)


def _blend_timevarying(frames: dict[str, pd.DataFrame], weights: pd.DataFrame) -> pd.DataFrame:
    """Weighted blend of family score frames with PER-DAY weights (dates × families), skipping NaN
    cells and renormalizing to the families present for each name each day (mirrors factors.blend,
    but the weights vary over time)."""
    fams = list(frames)
    base = frames[fams[0]]
    idx, cols = base.index, base.columns
    num = pd.DataFrame(0.0, index=idx, columns=cols)
    den = pd.DataFrame(0.0, index=idx, columns=cols)
    for fam in fams:
        fa = frames[fam].reindex(index=idx, columns=cols)
        w_col = weights[fam].reindex(idx) if fam in weights.columns else pd.Series(1.0, index=idx)
        mask = fa.notna()
        num = num.add(fa.fillna(0.0).mul(w_col, axis=0).where(mask, 0.0))
        den = den.add(mask.mul(w_col.abs(), axis=0))
    return num.div(den.where(den > 0))


def timed_composite(family_scores: dict[str, pd.DataFrame], risk_score: pd.Series, *,
                    on_tilt: dict[str, float] = RISK_ON_TILT,
                    off_tilt: dict[str, float] = RISK_OFF_TILT, winsor: float = 3.0) -> pd.DataFrame:
    """Regime-timed multi-factor composite: blend the family scores with time-varying, regime-
    conditional weights, then re-standardize. Same shape/convention as factors.composite, so it drops
    straight into the same weight construction and backtester — the ONLY difference from the static
    composite is that the family mix breathes with the macro regime."""
    fams = list(family_scores)
    w = regime_family_weights(risk_score.reindex(next(iter(family_scores.values())).index),
                              fams, on_tilt=on_tilt, off_tilt=off_tilt)
    return fac.standardize(_blend_timevarying(family_scores, w), winsor)


def apply_regime_exposure(book_returns: pd.Series, risk_score: pd.Series, *,
                          floor: float = 0.0, cap: float = 1.0) -> pd.Series:
    """Scale a book's return stream by the causal risk-appetite score (exposure timing): cut gross in
    risk-off, run it in risk-on. `floor`/`cap` bound the multiplier. This is the drawdown-control
    lever — it re-times exposure, so on a dollar-neutral book it mostly reshapes the path, while on a
    directional book it cuts the deep drawdowns (see run_macro for the same mechanism)."""
    mult = risk_score.reindex(book_returns.index).clip(floor, cap)
    return (book_returns * mult).rename(book_returns.name)


def risk_budget(book_returns: pd.Series, target_annual_vol: float = 0.10, *, window: int = 21,
                max_leverage: float = 3.0) -> pd.Series:
    """Vol-target the whole book to a constant risk budget (Moreira–Muir style, causal). Thin wrapper
    over portfolio.vol_managed — the final sleeve of the construction stack: whatever the composite
    and the regime overlay produce, the book is sized to a stable annualized volatility so risk is
    constant through time rather than drifting with the cross-section's own vol."""
    return pf.vol_managed(book_returns, target_annual_vol=target_annual_vol, window=window,
                          max_leverage=max_leverage)
