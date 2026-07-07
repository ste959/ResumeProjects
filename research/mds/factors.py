"""Multi-factor composite — turning many weak signals into one risk-controlled score.

Every single-factor study in this layer (run_crosssec, run_fundamentals) came back null on this
universe: no standalone signal clears the Deflated-Sharpe / Bonferroni bar. That is exactly what
Grinold–Kahn's *Fundamental Law of Active Management* predicts — the information ratio is

        IR ≈ IC · √breadth,

and on ~123 mega-caps breadth is tiny, so even a decent IC produces a mediocre IR. The escape is
not a cleverer single signal but MORE INDEPENDENT FORECASTS combined: several low-correlation
signals, grouped into economic FAMILIES (value / quality / momentum / reversal / low-risk / flow),
each standardized and blended within family, then the families blended into ONE composite score.
Diversifying across weakly-correlated factors raises the *effective* breadth and lowers the noise
of the aggregate forecast — the core of every systematic-equity book (AQR, Citadel EQR, Two Sigma).

This module only *combines* signals other modules produce (crosssec.signals for price/volume,
edgar.fundamental_signals for fundamentals); it never looks at returns to fit weights, so it adds
no look-ahead. Each score is a dates × symbols frame, higher = long, on the same convention the
backtester consumes. The composite is traded into the t→t+1 return by the same honest harness as
the single factors, so a composite that does not beat its parts is named as such.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Economic families. Each maps to the signal keys (from crosssec.signals + edgar.fundamental_signals)
# that express the same underlying bet. Grouping first — rather than throwing 18 signals into one
# average — stops a family that happens to have many members (e.g. low-risk) from dominating, and
# makes the composite's exposures interpretable (you can read its value vs quality vs momentum tilt).
FAMILIES: dict[str, list[str]] = {
    # cheapness — long high earnings/price (the one true fundamental value axis the free feed lacks)
    "value": ["earnings_yield"],
    # profitability / earnings-quality / conservative investment — the Novy-Marx / Sloan / CGS block
    "quality": ["gross_profitability", "roe", "accruals", "asset_growth"],
    # 12–1 trend, its sector-relative and risk-adjusted cousins, and the overnight-drift premium
    "momentum": ["momentum", "risk_adj_mom", "sector_rel_mom", "overnight"],
    # short-horizon mean-reversion (raw, sector-relative, and the close-vs-VWAP pressure variant)
    "reversal": ["reversal", "sector_rel_rev", "vwap_pressure"],
    # defensive / low-risk anomalies — low vol, betting-against-beta, low idio-vol, anti-lottery
    "low_risk": ["low_vol", "bab", "idio_vol", "max_lottery"],
    # daily-bar order-flow proxies — signed-volume pressure and institutional-participation trend
    "flow": ["flow_pressure", "trade_size_trend"],
}

# The medium-to-long-horizon RETURN-PREMIUM families — the classic systematic-equity factors
# (Fama–French value + momentum, Novy-Marx/AQR quality). This subset is the default alpha for a
# medium-term book, chosen a priori by HORIZON, not by peeking at realized Sharpes: `reversal` and
# `flow` are short-horizon microstructure signals (days, high turnover — the wrong clock for a
# medium-term composite), and `low_risk`/BAB is a defensive premium better expressed by scaling
# exposure (see factortiming.risk_budget) than as a long/short sleeve. They stay in FAMILIES for
# completeness and are reported for transparency, but are not blended into the medium-term composite.
MEDIUM_TERM_FAMILIES = ["value", "quality", "momentum"]


def medium_term_families() -> dict[str, list[str]]:
    """The return-premium family map (value/quality/momentum) — the default for a medium-term book."""
    return {k: FAMILIES[k] for k in MEDIUM_TERM_FAMILIES}


def _xs_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score each day (demean and scale across symbols, excluding NaNs)."""
    mean = frame.mean(axis=1)
    std = frame.std(axis=1).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0)


def standardize(frame: pd.DataFrame, winsor: float = 3.0) -> pd.DataFrame:
    """Cross-sectional z-score, then WINSORIZE to ±`winsor` and re-standardize.

    Winsorizing before combining is not cosmetic: a single outlier name (a data glitch, a 10-bagger)
    can otherwise swing the whole day's composite and drive turnover. Clipping the z-scores at ±3σ
    and re-standardizing bounds any one name's influence while keeping the cross-sectional ranking."""
    z = _xs_zscore(frame)
    if winsor and winsor > 0:
        z = z.clip(lower=-winsor, upper=winsor)
        z = _xs_zscore(z)          # re-standardize so each day is unit-variance after clipping
    return z


def blend(frames: list[pd.DataFrame], weights: list[float] | None = None) -> pd.DataFrame:
    """Weighted average of aligned frames, SKIPPING NaNs per cell so a name missing one input is
    still scored on the inputs it has (re-weighting to the present ones). Returns NaN only where a
    cell is missing from every input. This is what lets a name with no fundamentals still receive a
    price-only composite instead of dropping out of the book."""
    if not frames:
        raise ValueError("no frames to blend")
    if weights is None:
        weights = [1.0] * len(frames)
    if len(weights) != len(frames):
        raise ValueError("weights/frames length mismatch")
    base = frames[0]
    idx, cols = base.index, base.columns
    num = pd.DataFrame(0.0, index=idx, columns=cols)
    den = pd.DataFrame(0.0, index=idx, columns=cols)
    for f, w in zip(frames, weights):
        fa = f.reindex(index=idx, columns=cols)
        mask = fa.notna()
        num = num.add((fa.fillna(0.0) * w).where(mask, 0.0))
        den = den.add(mask.astype(float) * abs(w))
    return num.div(den.where(den > 0))


def family_scores(signals: dict[str, pd.DataFrame], families: dict[str, list[str]] = FAMILIES,
                  winsor: float = 3.0) -> dict[str, pd.DataFrame]:
    """One standardized score per family — the equal-weight blend of its members' z-scores.

    Members present in `signals` are each standardized (winsorized z), blended cell-wise skipping
    NaNs, then the family score is re-standardized so every family enters the composite on the same
    unit-variance scale (no family dominates through a wider raw spread). Families with no present
    member are omitted."""
    out: dict[str, pd.DataFrame] = {}
    for fam, members in families.items():
        present = [standardize(signals[m], winsor) for m in members if m in signals]
        if not present:
            continue
        out[fam] = standardize(blend(present), winsor)
    return out


def composite(signals: dict[str, pd.DataFrame], families: dict[str, list[str]] = FAMILIES,
              weights: dict[str, float] | None = None, winsor: float = 3.0) -> pd.DataFrame:
    """The single multi-factor score — a weighted blend of the family scores (higher = long).

    `weights` is a family→weight map (default equal weight across the families that are present).
    The result is re-standardized to a unit-variance cross-section each day so it plugs straight into
    the same z-score-to-weights construction the single-factor books use."""
    fams = family_scores(signals, families, winsor)
    if not fams:
        raise ValueError("no families could be built from the given signals")
    names = list(fams)
    w = [(weights or {}).get(n, 1.0) for n in names]
    return standardize(blend([fams[n] for n in names], w), winsor)


def ic_series(score: pd.DataFrame, fwd_ret: pd.DataFrame, min_names: int = 5) -> pd.Series:
    """Daily cross-sectional information coefficient — the rank correlation between today's score and
    the NEXT period's return. A diagnostic only (it looks one step ahead, so never feed it back into
    the live weights): the mean IC and its t-stat tell you whether the composite actually forecasts."""
    s = score.shift(1)                                  # score known at t-1 vs return at t (causal)
    out = {}
    for dt, row in fwd_ret.iterrows():
        a, b = s.loc[dt], row
        m = a.notna() & b.notna()
        if m.sum() >= min_names:
            out[dt] = a[m].corr(b[m], method="spearman")
    return pd.Series(out).dropna()


def ic_summary(ic: pd.Series) -> dict:
    """Mean IC, its IID t-stat, and the information ratio of the IC series (mean/std). A mean IC of a
    few percent with a t-stat > 2 is the systematic-equity standard for a usable forecast."""
    ic = ic.dropna()
    n = len(ic)
    sd = float(ic.std(ddof=0))
    return {
        "mean_ic": float(ic.mean()) if n else float("nan"),
        "ic_std": sd,
        "ic_ir": float(ic.mean() / sd) if sd > 0 else float("nan"),
        "t_stat": float(ic.mean() / sd * np.sqrt(n)) if sd > 0 and n else float("nan"),
        "n": n,
    }
