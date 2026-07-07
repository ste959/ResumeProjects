"""Overfitting- and autocorrelation-aware validation — the statistics a research review actually
demands, computed rather than asserted.

A positive backtest Sharpe is cheap; the honest questions are (1) is it distinguishable from zero
once you stop pretending the returns are IID, and (2) is it distinguishable from the *best of many
tries* you ran to find it. This module answers both:

  * `newey_west_sharpe_tstat` — HAC (Newey–West) t-stat; deflates the naive IID t when returns are
    autocorrelated (overlapping-window signals always are).
  * `block_bootstrap_sharpe_ci` — a non-parametric CI that makes no distributional assumption.
  * `deflated_sharpe` — Bailey & López de Prado's Deflated Sharpe: the probability the true Sharpe
    is positive AFTER accounting for how many strategies were tried (multiple testing) and for the
    return skew/kurtosis.
  * `pbo` — Probability of Backtest Overfitting via combinatorially-symmetric cross-validation:
    how often the in-sample-best strategy underperforms the field out-of-sample.

None of these manufacture significance; they take it away where it wasn't real.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np

TRADING_DAYS = 252


def _clean(returns) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    return r[np.isfinite(r)]


def _nw_bandwidth(n: int) -> int:
    """Newey–West automatic lag: floor(4·(n/100)^(2/9))."""
    return max(1, int(np.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


def newey_west_sharpe_tstat(returns, max_lag: int | None = None) -> float:
    """HAC t-stat for Sharpe ≠ 0. Testing Sharpe = 0 is testing mean return = 0, so the t-stat is
    √n·mean / √(long-run variance), where the long-run variance uses Bartlett-weighted
    autocovariances. With no autocorrelation this equals the IID t; positive autocorrelation
    (overlapping-window signals) inflates the long-run variance and DEFLATES the t."""
    r = _clean(returns)
    n = len(r)
    if n < 4:
        return 0.0
    mu = r.mean()
    dev = r - mu
    gamma0 = float(dev @ dev) / n
    lrv = gamma0
    L = max_lag if max_lag is not None else _nw_bandwidth(n)
    for lag in range(1, min(L, n - 1) + 1):
        w = 1.0 - lag / (L + 1.0)          # Bartlett kernel
        cov = float(dev[lag:] @ dev[:-lag]) / n
        lrv += 2.0 * w * cov
    if lrv <= 0:
        return 0.0
    return float(np.sqrt(n) * mu / np.sqrt(lrv))


def block_bootstrap_sharpe_ci(returns, n_boot: int = 2000, block: int | None = None,
                              ppy: int = TRADING_DAYS, seed: int = 0,
                              alpha: float = 0.05) -> tuple[float, float]:
    """Moving-block-bootstrap CI for the annualized Sharpe — resampling contiguous blocks
    preserves autocorrelation, so the interval is honest about serial dependence. Distribution-free."""
    r = _clean(returns)
    n = len(r)
    if n < 8:
        return (float("nan"), float("nan"))
    if block is None:
        block = max(1, int(round(n ** (1.0 / 3.0))))       # ~n^(1/3) rule of thumb
    block = min(block, n)
    n_blocks = int(np.ceil(n / block))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, n_blocks * block)[:, :n]
    samples = r[idx]
    mu = samples.mean(axis=1)
    sd = samples.std(axis=1, ddof=0)
    sharpes = np.where(sd > 0, np.sqrt(ppy) * mu / sd, 0.0)
    lo, hi = np.percentile(sharpes, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def deflated_sharpe(sharpe_ppp: float, n_obs: int, skew: float, kurt: float,
                    n_trials: int, sharpe_var_across_trials: float) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado, 2014): the probability the TRUE Sharpe is
    positive, after (a) correcting for return skew/kurtosis and (b) deflating by the expected
    maximum Sharpe you'd see from `n_trials` independent tries even with no real skill.

    Inputs are per-period (e.g. daily) quantities: `sharpe_ppp` the per-period Sharpe, `skew`/`kurt`
    the return skew and (non-excess) kurtosis, `sharpe_var_across_trials` the variance of the
    per-period Sharpes across the strategies tried. Returns a probability in [0, 1]; > 0.95 is the
    usual bar for a genuinely significant, selection-adjusted result."""
    from scipy.stats import norm

    if n_obs < 4:
        return float("nan")
    euler = 0.5772156649015329
    if n_trials >= 2 and sharpe_var_across_trials > 0:
        sd_trials = np.sqrt(sharpe_var_across_trials)
        sr0 = sd_trials * ((1 - euler) * norm.ppf(1 - 1.0 / n_trials)
                           + euler * norm.ppf(1 - 1.0 / (n_trials * np.e)))
    else:
        sr0 = 0.0
    var_sr = (1.0 - skew * sharpe_ppp + (kurt - 1.0) / 4.0 * sharpe_ppp ** 2) / (n_obs - 1)
    if var_sr <= 0:
        return float("nan")
    return float(norm.cdf((sharpe_ppp - sr0) / np.sqrt(var_sr)))


def pbo(returns_matrix, n_splits: int = 12) -> dict:
    """Probability of Backtest Overfitting via combinatorially-symmetric cross-validation
    (Bailey, Borwein, López de Prado, Zhu, 2016). Split time into S blocks; for every way of
    choosing S/2 blocks as in-sample, pick the IS-best strategy and measure its OUT-of-sample rank.
    PBO = fraction of splits where the IS-best strategy lands below the OOS median — i.e. how often
    'the best backtest' is really just the luckiest overfit. High PBO (→0.5+) means the selection is
    not trustworthy. `returns_matrix` is (T periods × M strategies)."""
    R = np.asarray(returns_matrix, dtype=float)
    if R.ndim != 2 or R.shape[1] < 2:
        return {"pbo": float("nan"), "n_combos": 0, "n_strategies": int(R.shape[1] if R.ndim == 2 else 0)}
    T, M = R.shape
    S = n_splits - (n_splits % 2)                 # force even
    bounds = np.linspace(0, T, S + 1).astype(int)
    blocks = [np.arange(bounds[i], bounds[i + 1]) for i in range(S)]

    def sharpe_cols(idx):
        sub = R[idx]
        mu = sub.mean(axis=0)
        sd = sub.std(axis=0, ddof=0)
        return np.where(sd > 0, mu / sd, 0.0)

    logits = []
    for combo in combinations(range(S), S // 2):
        oos = [i for i in range(S) if i not in combo]
        is_sh = sharpe_cols(np.concatenate([blocks[i] for i in combo]))
        oos_sh = sharpe_cols(np.concatenate([blocks[i] for i in oos]))
        best = int(np.argmax(is_sh))
        # relative OOS rank of the IS-best strategy (1 = best of the field)
        w = (oos_sh <= oos_sh[best]).sum() / M
        w = min(max(w, 1e-6), 1 - 1e-6)
        logits.append(np.log(w / (1 - w)))
    logits = np.asarray(logits)
    return {"pbo": float((logits < 0).mean()), "n_combos": len(logits), "n_strategies": M}
