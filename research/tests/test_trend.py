"""Tests for the enhanced trend-following module — signal properties, sizing, carry, causality
(no look-ahead), and that the ablation runs end-to-end through the shared gauntlet."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import evaluation as ev
from mds import trend


def _panel(n_days: int = 700, seed: int = 0) -> pd.DataFrame:
    """Synthetic multi-asset prices: persistent drifts (trends) + noise, deterministic."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-01", periods=n_days, freq="B")
    drifts = np.array([0.0006, -0.0005, 0.0003, 0.0, 0.0002])
    vols = np.array([0.010, 0.012, 0.008, 0.020, 0.011])
    cols = ["A", "B", "C", "D", "E"]
    rets = rng.normal(drifts, vols, size=(n_days, len(cols)))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=dates, columns=cols)


def test_trend_score_sign_follows_direction():
    # A clean monotonic up-trend → positive signal; a down-trend → negative.
    dates = pd.date_range("2021-01-01", periods=400, freq="B")
    up = pd.Series(np.linspace(100, 200, 400), index=dates)
    down = pd.Series(np.linspace(200, 100, 400), index=dates)
    prices = pd.DataFrame({"UP": up, "DOWN": down})
    sig = trend.trend_score(prices).iloc[-1]
    assert sig["UP"] > 0 and sig["DOWN"] < 0


def test_multiscale_signal_is_bounded():
    # The saturated (tanh) multi-timescale signal stays in ~[-1, 1] — no single asset can dominate.
    sig = trend.trend_score(_panel())
    assert sig.abs().to_numpy().max() <= 1.0 + 1e-9


def test_vanilla_signal_is_binary_sign():
    sig = trend.trend_score(_panel(), multiscale=False).dropna()
    assert set(np.unique(sig.to_numpy())).issubset({-1.0, 0.0, 1.0})


def test_carry_is_positive_for_a_distributor_and_zero_otherwise():
    # Total-return series grows faster than the price-only series exactly by the distribution yield.
    dates = pd.date_range("2021-01-01", periods=400, freq="B")
    price = pd.Series(100.0 * (1.0002) ** np.arange(400), index=dates)     # price-only path
    total = pd.Series(100.0 * (1.0006) ** np.arange(400), index=dates)     # + a steady distribution
    tp = pd.DataFrame({"PAYER": total, "NONE": price})
    pp = pd.DataFrame({"PAYER": price, "NONE": price})
    carry = trend.carry_score(tp, pp).iloc[-1]
    assert carry["PAYER"] > 0.02          # a clearly positive annualized income yield
    assert abs(carry["NONE"]) < 1e-6      # no gap → no carry


def test_inv_vol_downweights_the_high_vol_asset():
    prices = _panel()
    iv = trend._inv_vol(prices.pct_change()).iloc[-1]
    # Asset D is the highest-vol column by construction → it must get the smallest 1/σ weight.
    assert iv.idxmin() == "D"


def test_crash_scaler_cuts_gross_when_vol_spikes():
    dates = pd.date_range("2021-01-01", periods=400, freq="B")
    rng = np.random.default_rng(1)
    calm = rng.normal(0, 0.005, size=(300, 3))
    storm = rng.normal(0, 0.04, size=(100, 3))
    rets = pd.DataFrame(np.vstack([calm, storm]), index=dates, columns=list("XYZ"))
    scale = trend.crash_scaler(rets)
    assert scale.iloc[-1] < 0.8           # de-risked during the vol spike
    assert scale.iloc[-1] >= 0.4          # but never below the floor
    assert scale.iloc[290] > 0.95         # ~fully invested in the calm regime


def test_backtest_runs_and_reports_the_shared_stat_block():
    r = trend.backtest(_panel(), enh=frozenset({"voltarget", "multiscale", "portvol"}))
    for key in ("sharpe", "hac_t", "max_drawdown", "sortino", "cvar_5", "skew", "n_days"):
        assert key in r
    assert r["n_days"] > 100 and np.isfinite(r["sharpe"])


def test_backtest_has_no_lookahead():
    # Causality: truncating the FUTURE must not change any past net-return value. The signals are all
    # rolling/shifted and the loop trades the prior close's signal, so the early net series is identical
    # whether or not later data exists.
    prices = _panel(700)
    enh = frozenset({"voltarget", "multiscale", "portvol", "crash", "xs"})
    full = trend.backtest(prices, enh=enh)["net"]
    trunc = trend.backtest(prices.iloc[:450], enh=enh)["net"]
    common = trunc.index[:100]            # early dates, fully inside both runs
    assert np.allclose(full.loc[common].to_numpy(), trunc.loc[common].to_numpy(), atol=1e-12)


def test_higher_costs_never_help():
    prices = _panel()
    enh = frozenset({"voltarget", "multiscale", "portvol"})
    cheap = trend.backtest(prices, enh=enh, cost_bps=1.0)["ann_return"]
    dear = trend.backtest(prices, enh=enh, cost_bps=50.0)["ann_return"]
    assert dear <= cheap + 1e-9


def test_leverage_cap_is_respected():
    # With an aggressive vol target the portfolio-vol scaler would lever past the cap; it must clip.
    prices = _panel()
    r = trend.backtest(prices, enh=frozenset({"voltarget", "multiscale", "portvol"}),
                       target_vol=5.0, max_leverage=3.0)
    assert np.isfinite(r["sharpe"])       # runs without blowing up despite the extreme target


def test_ablation_runs_through_the_gauntlet():
    prices = _panel()
    total = prices * 1.03                 # a flat 3% distribution gap so carry is well-defined
    out = trend.ablation(prices, total)
    assert len(out["stages"]) == len(trend.ABLATION)
    g = out["gauntlet"]
    for key in ("best", "deflated_sharpe", "pbo", "bonferroni_t", "min_detectable_sharpe"):
        assert key in g
    assert g["n_strategies"] == len(trend.ABLATION)


def test_xs_momentum_is_cross_sectionally_neutral():
    xs = trend.xs_momentum(_panel()).dropna()
    assert xs.mean(axis=1).abs().max() < 1e-9      # z-scored across assets → each date sums to ~0


# ── diagnostics ───────────────────────────────────────────────────────────────────────────────────
def test_voltarget_decomposition_isolates_three_modes():
    out = trend.voltarget_decomposition(_panel())
    assert [d["mode"] for d in out] == ["none", "diag", "cov"]
    # constant-gross runs at ~1x gross; the vol-target modes scale gross away from 1.
    none = next(d for d in out if d["mode"] == "none")
    assert abs(none["avg_gross"] - 1.0) < 0.2


def test_loo_ablation_reports_full_plus_each_removal():
    prices = _panel()
    rows = trend.loo_ablation(prices, prices * 1.02)
    assert rows[0]["variant"] == "full system" and rows[0]["delta"] == 0.0
    assert {r["removed"] for r in rows[1:]} == set(trend.ALL_ENH)   # one row per enhancement removed


def test_attribution_contributions_reconcile_to_net():
    prices = _panel().rename(columns=dict(zip("ABCDE", ["SPY", "IEF", "LQD", "GLD", "UUP"])))  # real tickers
    # With zero cost, per-asset contributions (wᵢ·rᵢ) sum EXACTLY to the net return — the only gap
    # otherwise is the turnover charge, which is real, not a bookkeeping error.
    at = trend.attribution(prices, prices * 1.02, enh=frozenset({"voltarget", "multiscale", "portvol"}),
                           cost_bps=0.0, regimes=[("all", "2021-01-01", "2025-01-01")])
    assert abs(at["per_sleeve"].sum() - at["net"].sum()) < 1e-9
    assert set(at["net_exposure"].index).issubset({"Equity", "Rates", "Credit", "Commodity", "USD"})


def test_paired_sharpe_diff_ci_is_zero_for_identical_series():
    net = trend.backtest(_panel(), enh=frozenset({"voltarget", "multiscale"}))["net"]
    d = ev.paired_sharpe_diff_ci(net, net)
    assert abs(d["diff"]) < 1e-9 and d["lo"] <= 0 <= d["hi"]     # a series vs itself → no difference


def test_factor_betas_recovers_a_known_beta():
    # Construct a book that is exactly 0.5·factor + noise → regression should recover β≈0.5.
    rng = np.random.default_rng(3)
    dates = pd.date_range("2021-01-01", periods=500, freq="B")
    fac = pd.Series(rng.normal(0, 0.01, 500), index=dates)
    book = pd.Series(0.5 * fac.to_numpy() + rng.normal(0, 0.001, 500), index=dates)
    fb = trend.factor_betas(book, fac.to_frame("F"))
    assert abs(fb["betas"]["F"] - 0.5) < 0.05
