"""Cross-sectional statistical arbitrage — residual reversal on statistical (PCA) risk factors.

The canonical equity-desk strategy (Avellaneda–Lee 2010, "Statistical Arbitrage in the US Equities
Market"), and the honest test of whether this platform's methods find *alpha*, not just a decayed premium:

  1. **Statistical risk factors** — the top-k eigenvectors of the return correlation matrix are the
     "eigenportfolios" (≈ market + sectors). No fundamental sector data needed; the factors are *learned*.
  2. **Residualize** — regress each stock's returns on the factor returns; the residual is the
     idiosyncratic move, orthogonal to the common factors (so the book is **factor-neutral by construction**).
  3. **s-score** — model the cumulative residual as a mean-reverting **Ornstein–Uhlenbeck** process; the
     s-score is how many equilibrium-σ the residual sits from its mean. Trade names whose reversion is fast
     enough to matter (κ filter).
  4. **Portfolio** — alpha = −s-score (fade the deviation), risk-weighted by residual vol, **dollar-neutral**.

This is short-horizon and high-turnover, so it's the strategy where realistic execution cost decides
everything — exactly what the platform is built to measure. Pure NumPy; the `Strategy` subclass plugs
straight into `engine.run`. `run_xstatarb.py` runs it on a broad universe, gross vs. net.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import Strategy

TRADING_DAYS = 252


def _zscore(R: np.ndarray) -> np.ndarray:
    """Standardize each column (stock) of a return window; zero-vol columns become zeros."""
    mu, sd = R.mean(axis=0), R.std(axis=0)
    return np.divide(R - mu, sd, out=np.zeros_like(R), where=sd > 0)


def eigen_factor_returns(R: np.ndarray, k: int) -> np.ndarray:
    """Top-k eigenportfolio factor-return series over a return window (Avellaneda–Lee statistical factors).
    Standardizes returns, eigen-decomposes the (correlation-like) matrix, and projects onto the leading
    eigenvectors. Returns a window×k array of factor returns."""
    Rz = _zscore(R)
    C = np.nan_to_num(Rz.T @ Rz / max(len(R), 1))       # correlation-like (standardized) matrix
    vals, vecs = np.linalg.eigh(C)                       # ascending eigenvalues
    top = vecs[:, -k:]                                   # leading k eigenvectors (largest variance)
    return Rz @ top                                      # window×k factor returns


def residualize(R: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Residual returns after regressing each stock on the factor returns (+ intercept) — vectorized over
    all stocks. The residuals are orthogonal to the factors: this is the factor-neutralization."""
    X = np.column_stack([np.ones(len(F)), F])
    beta, *_ = np.linalg.lstsq(X, R, rcond=None)
    return R - X @ beta


def s_scores(resid: np.ndarray, kappa_min: float) -> np.ndarray:
    """The Avellaneda–Lee s-score for each stock: fit an OU process to the *cumulative* residual and
    report (current level − equilibrium) / equilibrium-σ. Vectorized AR(1) across stocks. Names that don't
    mean-revert (b∉(0,1)) or revert too slowly (κ < `kappa_min`) get s=0 (not traded)."""
    X = np.cumsum(resid - resid.mean(axis=0), axis=0)    # auxiliary OU process per stock
    x0, x1 = X[:-1], X[1:]
    x0m, x1m = x0.mean(axis=0), x1.mean(axis=0)
    var0 = ((x0 - x0m) ** 2).mean(axis=0)
    cov = ((x0 - x0m) * (x1 - x1m)).mean(axis=0)
    b = np.divide(cov, var0, out=np.zeros_like(var0), where=var0 > 0)   # AR(1) slope
    a = x1m - b * x0m
    ar_resid = x1 - (a + b * x0)
    var_ar = ar_resid.var(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        m = np.where((b > 0) & (b < 1), a / (1 - b), 0.0)              # OU equilibrium
        sigma_eq = np.sqrt(np.maximum(var_ar / (1 - b ** 2), 0.0))
        kappa = -np.log(np.clip(b, 1e-8, 1 - 1e-8))                    # mean-reversion speed (per period)
    s = np.divide(X[-1] - m, sigma_eq, out=np.zeros_like(m), where=sigma_eq > 0)
    tradable = (b > 0) & (b < 1) & (kappa > kappa_min)                 # fast-enough reversion only
    return np.where(tradable, s, 0.0)


class CrossSectionalStatArb(Strategy):
    """Residual-reversal stat-arb: long low-s-score (residual below equilibrium), short high-s-score,
    factor-neutral (by residualization) and dollar-neutral, risk-weighted by residual vol."""
    name = "statarb-reversal"

    def __init__(self, symbols: list[str], window: int = 60, k: int = 5, gross: float = 1.0):
        self._symbols = list(symbols)
        self.window, self.k, self.gross = window, k, gross
        self.warmup = window + 2
        # require the residual to mean-revert faster than half the window (else it's not tradable here)
        self._kappa_min = np.log(2) / (window / 2.0)

    def symbols(self) -> list[str]:
        return self._symbols

    def prepare(self, prices: pd.DataFrame) -> None:
        self._rets = prices.pct_change().to_numpy()

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        R = np.nan_to_num(self._rets[t - self.window:t])
        F = eigen_factor_returns(R, self.k)
        e = residualize(R, F)
        s = s_scores(e, self._kappa_min)
        alpha = -s                                       # fade the deviation
        rv = e.std(axis=0)
        w = np.divide(alpha, rv, out=np.zeros_like(alpha), where=rv > 0)   # risk-weight by residual vol
        w = w - w.mean()                                 # dollar-neutral
        g = np.abs(w).sum()
        return (w / g) * self.gross if g > 0 else w
