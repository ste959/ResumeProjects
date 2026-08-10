"""Implementation alpha — maximizing the *transfer coefficient* of a signal you already have.

Grinold–Kahn's Fundamental Law: `IR = IC · √breadth · TC`, where the **transfer coefficient** TC is the
fraction of a signal's theoretical performance that survives real-world implementation (risk limits, costs,
turnover, unintended factor bets). Alpha discovery moves IC; *implementation* moves TC — and for a junior
without HFT infrastructure, TC is where the realistic, defensible edge is. "I don't need a signal you don't
have; give me one you trust and I'll make more of it reach the P&L."

This takes a **standard, decayed signal** — cross-sectional 12–1 momentum — and layers the industry-standard
techniques a quant trader actually uses, each measurable for its incremental contribution:

  clean      — winsorize + cross-sectional z-score (kill outliers)
  neutralize — regress out **beta and size** (Barra-style) so it's *pure* momentum, not a hidden factor bet
  risk       — inverse-vol weighting + **volatility targeting** (constant portfolio vol)
  hedge      — short the index to zero the book's **market beta** (true market-neutral)
  smooth     — EWMA the signal + **no-trade bands** to cut turnover, hence cost

The signal never changes (IC is fixed); the *deployed* result improves. Reuses the engine, execution model,
and evaluation harness. Pure NumPy/pandas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import assetalloc as aa
from . import riskmodel as rm
from .engine import Strategy

TRADING_DAYS = 252


def pca_risk_model(R: np.ndarray, k: int = 5) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A statistical (PCA) factor risk model from a returns window: the top-k eigenvectors are the factor
    loadings B, their eigenvalues the factor covariance F, and the residual per-asset variance is the
    specific variance d — so Σ = BFBᵀ + diag(d) (Barra-style, but factors *learned* from the data). Feeds
    `riskmodel.asset_covariance` + `riskmodel.optimize` — the proper deployment tool, no fundamental data."""
    R = np.asarray(R, float)
    R = R - R.mean(axis=0)
    cov = np.cov(R, rowvar=False)
    vals, vecs = np.linalg.eigh(cov)
    idx = np.argsort(vals)[::-1][:k]
    B, fvar = vecs[:, idx], vals[idx]
    d = np.maximum(np.diag(cov) - np.sum((B ** 2) * fvar, axis=1), 1e-10)   # specific = total − systematic
    return B, np.diag(fvar), d

ABLATION = [
    ("raw signal", frozenset()),
    ("+ clean (winsor/z)", frozenset({"clean"})),
    ("+ neutralize (β,vol)", frozenset({"clean", "neutralize"})),
    ("+ risk sizing (vol-tgt)", frozenset({"clean", "neutralize", "risk"})),
    ("+ beta hedge", frozenset({"clean", "neutralize", "risk", "hedge"})),
    ("+ turnover control", frozenset({"clean", "neutralize", "risk", "hedge", "smooth", "bands"})),
]
FULL = ABLATION[-1][1]


def momentum_signal(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Cross-sectional 12–1 momentum: trailing return skipping the last month (the standard construction —
    the skip avoids short-term reversal contamination)."""
    return prices.shift(skip) / prices.shift(lookback) - 1.0


def information_coefficient(signal: pd.DataFrame, fwd_ret: pd.DataFrame) -> dict:
    """Rank IC: the cross-sectional Spearman correlation of the signal with next-period returns, averaged
    over time. Mean IC, IC-IR (Sharpe of the IC series), and its t-stat — the signal's *theoretical* power,
    unchanged by implementation."""
    ic = signal.shift(1).corrwith(fwd_ret, axis=1, method="spearman").dropna()
    return {"mean_ic": round(float(ic.mean()), 4),
            "ic_ir": round(float(ic.mean() / ic.std()), 3) if ic.std() > 0 else 0.0,
            "t_stat": round(float(ic.mean() / ic.std() * np.sqrt(len(ic))), 2) if ic.std() > 0 else 0.0}


def _winsor_z(s: pd.Series, z: float = 3.0) -> pd.Series:
    sd = s.std()
    return ((s - s.mean()) / sd).clip(-z, z) if sd > 0 else s * 0.0


def _neutralize(s: pd.Series, beta: pd.Series, vol: pd.Series) -> pd.Series:
    """Cross-sectional OLS residual of the signal on [1, beta, log-vol] — removes the part of momentum that's
    just a beta or volatility tilt (characteristic neutralization). Neutralizing the vol tilt is the standard
    fix for *momentum crashes* (winners are high-β/high-vol, which reverse violently — Barroso–Santa-Clara)."""
    df = pd.concat([s, beta, np.log(vol.clip(lower=1e-6))], axis=1).dropna()
    if len(df) < 10:
        return s
    X = np.column_stack([np.ones(len(df)), df.iloc[:, 1].to_numpy(), df.iloc[:, 2].to_numpy()])
    y = df.iloc[:, 0].to_numpy()
    beta_hat, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = pd.Series(y - X @ beta_hat, index=df.index)
    return resid.reindex(s.index)


class ImplementedMomentum(Strategy):
    """Cross-sectional momentum with a configurable stack of implementation layers (`enh`). The last symbol
    is the hedge instrument (index); the rest are the stock universe."""
    name = "momentum"

    def __init__(self, stocks: list[str], hedge: str = "SPY", enh: frozenset = FULL,
                 lookback: int = 252, skip: int = 21, target_vol: float = 0.08,
                 vol_window: int = 63, smooth_hl: int = 5, band: float = 0.002, beta_window: int = 126,
                 k_factors: int = 5, opt_window: int = 252, pos_cap: float = 0.10, max_turnover: float = 0.5):
        self._stocks = list(stocks)
        self.hedge = hedge
        self.enh = enh
        self.lookback, self.skip, self.target_vol = lookback, skip, target_vol
        self.vol_window, self.smooth_hl, self.band, self.beta_window = vol_window, smooth_hl, band, beta_window
        self.k_factors, self.opt_window, self.pos_cap, self.max_turnover = k_factors, opt_window, pos_cap, max_turnover
        self.warmup = max(lookback, opt_window) + 5
        self._prev = None
        self._prev_stock = None

    def symbols(self):
        return self._stocks + [self.hedge]

    def prepare(self, prices):
        px = prices[self._stocks]
        self._rets = px.pct_change()
        mom = momentum_signal(px, self.lookback, self.skip)
        self._mom = mom
        self._mom_smooth = mom.ewm(halflife=self.smooth_hl).mean()
        self._vol = self._rets.rolling(self.vol_window).std() * np.sqrt(TRADING_DAYS)
        hedge_ret = prices[self.hedge].pct_change()
        self._beta = self._rets.rolling(self.beta_window).cov(hedge_ret).div(
            hedge_ret.rolling(self.beta_window).var(), axis=0)                      # rolling market beta per stock

    def target_weights(self, prices, t):
        n = len(self.symbols())
        e = self.enh
        s = (self._mom_smooth if "smooth" in e else self._mom).iloc[t - 1].dropna()
        if s.empty:
            return np.zeros(n)
        if "clean" in e:
            s = _winsor_z(s)
        if "neutralize" in e:
            s = _neutralize(s, self._beta.iloc[t - 1], self._vol.iloc[t - 1]).dropna()
        if "optimize" in e:                                             # principled: the factor-risk-model optimizer
            return self._optimize_weights(s, t)
        w = s - s.mean()                                                # dollar-neutral
        if "risk" in e:
            w = w / self._vol.iloc[t - 1].reindex(w.index).replace(0, np.nan)      # inverse-vol
        w = w.dropna()
        g = w.abs().sum()
        if g > 0:
            w = w / g
        if "risk" in e and len(w) > 1:                                  # scale to a constant portfolio vol
            win = self._rets.iloc[t - self.vol_window:t][w.index].dropna(axis=1)
            if len(win.columns) > 1:
                wv = w.reindex(win.columns).fillna(0.0).to_numpy()
                pv = float(np.sqrt(max(wv @ aa._shrink_cov(win) @ wv, 0.0)))       # annualized book vol
                if pv > 0:
                    w = w * (self.target_vol / pv)

        full = pd.Series(0.0, index=self.symbols())
        full.loc[w.index] = w.to_numpy()
        if "hedge" in e:                                                # zero the book's net market beta
            net_beta = float((w * self._beta.iloc[t - 1].reindex(w.index)).sum())
            full.loc[self.hedge] = -net_beta
        vec = full.to_numpy()
        if "bands" in e and self._prev is not None:                     # no-trade band: skip tiny adjustments
            move = vec - self._prev
            vec = np.where(np.abs(move) < self.band, self._prev, vec)
        self._prev = vec
        return vec

    def _optimize_weights(self, s: pd.Series, t: int):
        """Size via the factor-risk-model constrained optimizer (`riskmodel.optimize`): maximize αᵀw − ½wᵀΣw
        s.t. dollar- and factor-neutrality (C·w = 0), a per-name box cap, and a turnover budget — Σ from a
        PCA factor risk model. The principled deployment path, replacing the ad-hoc inverse-vol/hedge stack."""
        n = len(self.symbols())
        win = self._rets.iloc[t - self.opt_window:t].dropna(axis=1)
        cols = list(win.columns)
        if len(cols) < self.k_factors + 2:
            return np.zeros(n)
        B, F, d = pca_risk_model(win.to_numpy(), self.k_factors)
        Sigma = rm.asset_covariance(B, F, d)                          # scale-invariant: optimize() gives w ∝ Σ⁻¹α
        a = s.reindex(cols).fillna(0.0).to_numpy()
        sd = a.std()
        if sd > 0:
            a = (a - a.mean()) / sd                                     # unit-std alpha → sane alpha/risk tradeoff
        C = np.vstack([np.ones((1, len(cols))), B.T])                  # dollar-neutral + factor-neutral
        wp = self._prev_stock.reindex(cols).fillna(0.0).to_numpy() if self._prev_stock is not None else None
        w = rm.optimize(a, Sigma, C, gross=1.0, position_cap=self.pos_cap, w_prev=wp, max_turnover=self.max_turnover)
        self._prev_stock = pd.Series(w, index=cols)
        full = pd.Series(0.0, index=self.symbols())
        full.loc[cols] = w
        return full.to_numpy()
