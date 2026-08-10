"""Shared, strategy-agnostic evaluation harness — the *same measuring stick* for every study.

Any strategy that produces a **net daily return series** (asset allocation, trend-following, …) is
judged here: excess-of-cash returns, an honest stat block (annualized return/vol, EXCESS Sharpe with a
Newey–West t-stat and a block-bootstrap CI, drawdown, and the downside/tail metrics Sharpe hides), and
a selection-aware `gauntlet` over a *set* of strategies (PBO, Deflated Sharpe of the best, the
multiple-testing t-bar, and the min-detectable Sharpe power check).

Factored out of `assetalloc.py` so `trend.py` and future studies reuse it verbatim rather than
re-implementing (and subtly diverging from) the honest accounting. Pure NumPy/pandas — no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sstats

from . import validation as val

TRADING_DAYS = 252


def excess(net: pd.Series, rf: pd.Series | None) -> np.ndarray:
    """Return in EXCESS of the daily risk-free rate — the correct basis for a Sharpe (a risk *premium*).
    Over 2020-26 cash went from ~0% to ~5%, so ignoring it materially overstates every Sharpe."""
    r = net.to_numpy(dtype=float)
    if rf is None:
        return r
    rf_a = np.nan_to_num(rf.reindex(net.index).to_numpy(dtype=float))
    return r - rf_a


ZERO_STATS = {"ann_return": 0.0, "ann_vol": 0.0, "sharpe": 0.0, "hac_t": 0.0, "boot_lo": 0.0,
              "boot_hi": 0.0, "max_drawdown": 0.0, "sortino": 0.0, "calmar": 0.0, "cvar_5": 0.0,
              "skew": 0.0, "n_days": 0}


def stats(net: pd.Series, rf: pd.Series | None = None, ppy: int = TRADING_DAYS) -> dict:
    """Honest stat block for one net-return series. Sharpe/Sortino are computed on EXCESS-of-cash
    returns; return/vol/drawdown/skew on the raw series. Guards degenerate inputs to `ZERO_STATS`."""
    r = net.to_numpy(dtype=float)
    ex = excess(net, rf)                              # excess-of-cash return series
    m = np.isfinite(r)
    r, ex = r[m], ex[m]
    if len(r) < 8 or ex.std() == 0:
        return {**ZERO_STATS, "n_days": len(r)}
    prod = float(np.prod(1 + r))
    ann_ret = float(prod ** (ppy / len(r)) - 1) if prod > 0 else -1.0   # total (undefined if wiped out)
    ann_vol = float(r.std() * np.sqrt(ppy))
    sharpe = float(ex.mean() / ex.std() * np.sqrt(ppy))                 # EXCESS Sharpe (risk premium)
    hac_t = float(val.newey_west_sharpe_tstat(ex))
    lo, hi = val.block_bootstrap_sharpe_ci(ex, ppy=ppy)
    equity = np.cumprod(1 + r)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.where(peak > 0, equity / peak - 1.0, 0.0).min())
    # tail / downside risk — Sharpe & vol treat up and down symmetrically; these don't.
    downside = ex[ex < 0]
    sortino = float(ex.mean() / downside.std() * np.sqrt(ppy)) if len(downside) and downside.std() > 0 else 0.0
    calmar = float(ann_ret / abs(max_dd)) if max_dd < 0 else 0.0
    var5 = float(np.percentile(r, 5))
    cvar5 = float(r[r <= var5].mean()) if (r <= var5).any() else var5   # 5% expected shortfall (daily)
    return {"ann_return": round(ann_ret, 4), "ann_vol": round(ann_vol, 4), "sharpe": round(sharpe, 3),
            "hac_t": round(hac_t, 2), "boot_lo": round(float(lo), 2), "boot_hi": round(float(hi), 2),
            "max_drawdown": round(max_dd, 4), "sortino": round(sortino, 3), "calmar": round(calmar, 2),
            "cvar_5": round(cvar5, 5), "skew": round(float(sstats.skew(r)), 3), "n_days": len(r)}


def paired_sharpe_diff_ci(net_a: pd.Series, net_b: pd.Series, rf: pd.Series | None = None,
                          n_boot: int = 2000, block: int | None = None, ppy: int = TRADING_DAYS,
                          seed: int = 0) -> dict:
    """Block-bootstrap CI for the DIFFERENCE in excess Sharpe between two strategies, **paired** on the
    same dates (each resample draws the same time blocks for both series, so the common market moves
    cancel). Answers 'is strategy A really better than B, or is the gap sampling noise?' — the question a
    table of point estimates can't. Deterministic (fixed seed). Returns diff and a 95% CI; a CI spanning
    0 means the improvement is not distinguishable from luck on this sample."""
    common = net_a.index.intersection(net_b.index)
    a, b = excess(net_a.reindex(common), rf), excess(net_b.reindex(common), rf)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    n = len(a)
    if n < 30:
        return {"diff": 0.0, "lo": 0.0, "hi": 0.0, "n": n}

    def sr(x: np.ndarray) -> float:
        sd = x.std()
        return float(x.mean() / sd * np.sqrt(ppy)) if sd > 0 else 0.0

    diff = sr(a) - sr(b)
    block = block or max(5, int(round(n ** (1 / 3))))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]   # same idx for both = paired
        diffs[i] = sr(a[idx]) - sr(b[idx])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"diff": round(diff, 3), "lo": round(float(lo), 3), "hi": round(float(hi), 3), "n": n}


def gauntlet(nets: dict, rf: pd.Series | None = None) -> dict:
    """Selection-aware honesty on a strategy SET: PBO across all of them, the Deflated Sharpe of the
    best (deflated for having tried this many), the multiple-testing t-bar, and the min-detectable
    Sharpe — is the sample even powered to distinguish these from luck? All on excess-of-cash returns."""
    raw = pd.DataFrame(nets).dropna()               # T × M aligned net-return matrix
    mat = raw.apply(lambda col: pd.Series(excess(col, rf), index=col.index))   # excess of cash
    n, m = mat.shape
    pp = mat.mean() / mat.std(ddof=0)               # per-period excess Sharpe of each strategy
    best = str(pp.idxmax())
    r_best = mat[best].to_numpy()
    dsr = float(val.deflated_sharpe(float(pp[best]), n, float(sstats.skew(r_best)),
                                    float(sstats.kurtosis(r_best, fisher=False)),  # non-excess kurtosis
                                    m, float(np.var(pp.to_numpy(), ddof=1))))
    return {
        "best": best,
        "best_sharpe_ann": round(float(pp[best]) * np.sqrt(TRADING_DAYS), 3),
        "best_hac_t": round(float(val.newey_west_sharpe_tstat(r_best)), 2),
        "bonferroni_t": round(float(val.bonferroni_z(m)), 2),
        "deflated_sharpe": round(dsr, 3),
        "pbo": round(float(val.pbo(mat.to_numpy())["pbo"]), 3),
        "min_detectable_sharpe": round(float(val.min_detectable_sharpe(n, ppy=TRADING_DAYS)), 2),
        "n_strategies": m, "n_days": n,
    }
