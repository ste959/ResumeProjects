"""Hand-rolled econometrics for pairs research — no statsmodels dependency.

Implements ordinary least squares, the Augmented Dickey–Fuller unit-root test, the
Engle–Granger two-step cointegration test, and the Ornstein–Uhlenbeck half-life of
mean reversion. Written from the definitions so the method is explicit rather than a
library call.
"""

from __future__ import annotations

import numpy as np

# MacKinnon critical values.
# Plain ADF unit-root test (constant, no trend), asymptotic:
ADF_CRIT = {"1%": -3.43, "5%": -2.86, "10%": -2.57}
# Engle–Granger residual-based cointegration test, 2 variables, constant:
COINT_CRIT = {"1%": -3.90, "5%": -3.34, "10%": -3.04}


def ols(X: np.ndarray, y: np.ndarray) -> dict:
    """Ordinary least squares. X already includes any intercept column.

    Returns beta, standard errors, t-stats and residuals.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    dof = max(n - k, 1)
    sigma2 = float(resid @ resid) / dof
    xtx_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.maximum(np.diag(sigma2 * xtx_inv), 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        tstat = np.where(se > 0, beta / se, 0.0)
    return {"beta": beta, "se": se, "tstat": tstat, "resid": resid}


def adf(series: np.ndarray, lags: int = 1) -> float:
    """Augmented Dickey–Fuller test statistic (constant, no trend).

    Regresses Δy_t on [const, y_{t-1}, Δy_{t-1..t-lags}] and returns the t-stat on the
    y_{t-1} coefficient. More negative ⇒ stronger evidence the series is stationary.
    """
    y = np.asarray(series, dtype=float)
    dy = np.diff(y)
    n = len(dy)
    if n <= lags + 2:
        return 0.0
    # Rows are valid for t = lags .. n-1 (need `lags` past differences).
    start = lags
    target = dy[start:]
    ylag = y[start:n]  # y_{t-1} aligned with dy[start:]
    cols = [np.ones_like(target), ylag]
    for i in range(1, lags + 1):
        cols.append(dy[start - i:n - i])
    X = np.column_stack(cols)
    fit = ols(X, target)
    return float(fit["tstat"][1])  # t-stat on y_{t-1}


def engle_granger(y: np.ndarray, x: np.ndarray, lags: int = 1) -> dict:
    """Engle–Granger two-step cointegration test.

    Step 1: regress y on x (with intercept) → hedge ratio beta and residual spread.
    Step 2: ADF test on the residuals. If the residuals are stationary, y and x are
    cointegrated (a mean-reverting linear combination exists).
    """
    y = np.asarray(y, dtype=float)
    x = np.asarray(x, dtype=float)
    fit = ols(np.column_stack([np.ones_like(x), x]), y)
    alpha, beta = float(fit["beta"][0]), float(fit["beta"][1])
    resid = fit["resid"]
    stat = adf(resid, lags=lags)
    return {
        "alpha": alpha,
        "beta": beta,
        "spread": resid,
        "adf_stat": stat,
        "crit": COINT_CRIT,
        "cointegrated_5pct": stat < COINT_CRIT["5%"],
    }


def half_life(spread: np.ndarray) -> float:
    """Ornstein–Uhlenbeck half-life of mean reversion, in observations.

    Fits Δspread_t = a + b·spread_{t-1}; half-life = -ln(2)/b for b < 0 (mean-reverting).
    Returns inf when the series shows no mean reversion.
    """
    s = np.asarray(spread, dtype=float)
    ds = np.diff(s)
    slag = s[:-1]
    fit = ols(np.column_stack([np.ones_like(slag), slag]), ds)
    b = float(fit["beta"][1])
    if b >= 0:
        return float("inf")
    return float(-np.log(2) / b)


def rolling_zscore(series: np.ndarray, window: int) -> np.ndarray:
    """Rolling z-score using a trailing window (NaN until the window fills)."""
    import pandas as pd

    s = pd.Series(np.asarray(series, dtype=float))
    mean = s.rolling(window).mean()
    std = s.rolling(window).std(ddof=0)
    z = (s - mean) / std
    return z.to_numpy()
