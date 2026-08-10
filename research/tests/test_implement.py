"""Tests for the implementation-alpha module — the momentum signal, IC, characteristic neutralization,
and the engine strategy's layers (dollar-neutrality, beta-hedge zeroing net beta)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import engine as eng
from mds import implement as im


def _panel(n=500, k=20, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    cols = [f"S{i}" for i in range(k)] + ["SPY"]
    rets = rng.normal(0.0003, 0.012, (n, k + 1))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=cols)


def test_momentum_is_12_1_return():
    px = _panel(400, 3)
    mom = im.momentum_signal(px, lookback=252, skip=21)
    exp = px["S0"].shift(21).iloc[300] / px["S0"].shift(252).iloc[300] - 1
    assert abs(mom["S0"].iloc[300] - exp) < 1e-12


def test_information_coefficient_runs_and_is_bounded():
    px = _panel()
    sig = im.momentum_signal(px[[c for c in px.columns if c != "SPY"]])
    fwd = px[[c for c in px.columns if c != "SPY"]].pct_change().shift(-1)
    ic = im.information_coefficient(sig, fwd)
    assert set(ic) == {"mean_ic", "ic_ir", "t_stat"} and abs(ic["mean_ic"]) <= 1


def test_winsor_z_clips_and_standardizes():
    s = pd.Series([1.0, 2, 3, 4, 100])
    z = im._winsor_z(s)
    assert z.abs().max() <= 3.0 + 1e-9 and abs(z.mean()) < 1e-9


def test_neutralize_removes_the_beta_tilt():
    # A signal that is exactly 2×beta should residualize to ~0 (fully explained by the beta characteristic).
    names = [f"S{i}" for i in range(20)]
    beta = pd.Series(np.linspace(0.5, 1.5, 20), index=names)
    vol = pd.Series(0.2, index=names)
    s = 2.0 * beta
    resid = im._neutralize(s, beta, vol)
    assert resid.abs().max() < 1e-6


def _stocks(px):
    return [c for c in px.columns if c != "SPY"]


def test_strategy_book_is_dollar_neutral_across_the_stocks():
    px = _panel()
    stocks = _stocks(px)
    r = eng.run(im.ImplementedMomentum(stocks, enh=frozenset({"clean", "neutralize"})), px,
                eng.BacktestConfig(rebalance=21, cost_bps=0.0))
    stock_w = r.weights[stocks]
    assert stock_w.sum(axis=1).abs().max() < 1e-6              # long/short stocks net to ~0


def test_pca_risk_model_reconstructs_the_covariance():
    rng = np.random.default_rng(0)
    R = rng.normal(0, 0.01, (400, 8))
    B, F, d = im.pca_risk_model(R, k=3)
    assert B.shape == (8, 3) and F.shape == (3, 3) and d.shape == (8,)
    assert (d > 0).all()
    # A low-rank factor model reconstructs the DIAGONAL exactly (systematic + specific = total variance)
    # and only approximates the off-diagonal — that's the whole point of a factor model.
    from mds import riskmodel as rm
    Sigma = rm.asset_covariance(B, F, d)
    cov = np.cov(R - R.mean(0), rowvar=False)
    assert np.abs(np.diag(Sigma) - np.diag(cov)).max() < 1e-8      # per-asset variance is exact
    assert np.allclose(Sigma, Sigma.T)                            # symmetric, well-formed


def test_risk_model_optimizer_book_is_dollar_and_factor_neutral():
    px = _panel(600)
    stocks = _stocks(px)
    r = eng.run(im.ImplementedMomentum(stocks, enh=frozenset({"clean", "optimize"}), opt_window=252, k_factors=3),
                px, eng.BacktestConfig(rebalance=21, cost_bps=0.0))
    w = r.weights[stocks]
    active = w.loc[(w.abs().sum(axis=1) > 0)]
    assert active.sum(axis=1).abs().max() < 1e-6            # dollar-neutral (the optimizer's C row of ones)
    assert (w[stocks].abs().max().max() <= 0.10 + 1e-6)    # position box cap respected


def test_beta_hedge_takes_a_position_in_the_index():
    px = _panel()
    stocks = _stocks(px)
    hedged = eng.run(im.ImplementedMomentum(stocks, enh=im.FULL), px, eng.BacktestConfig(rebalance=21, cost_bps=0.0))
    unhedged = eng.run(im.ImplementedMomentum(stocks, enh=frozenset({"clean", "neutralize", "risk"})), px,
                       eng.BacktestConfig(rebalance=21, cost_bps=0.0))
    assert hedged.weights["SPY"].abs().sum() > 0              # the hedge trades the index
    assert unhedged.weights["SPY"].abs().sum() == 0          # no hedge → no index position
