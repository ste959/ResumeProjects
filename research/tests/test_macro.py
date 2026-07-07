"""Tests for the FRED macro / credit overlay — the two properties that make the risk-off timing
signal trustworthy WITHOUT hitting the network: the score is (1) strictly causal, and (2) bounded
in [0,1]. Both are checked on a synthetic hy/vix frame injected via `frame=`, so no FRED call."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import macro as mc


def _synthetic_frame(n: int = 900, seed: int = 0) -> pd.DataFrame:
    """A synthetic daily hy/ig/vix frame with a risk-off spike partway through, so the score has
    real variation to test (calm → stress → calm)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    hy = 3.5 + np.cumsum(rng.normal(0, 0.03, n))
    vix = 16.0 + rng.normal(0, 1.5, n)
    # inject a risk-off episode in the middle: spreads and vol blow out
    lo, hi = n // 2, n // 2 + 40
    hy[lo:hi] += np.linspace(0, 4.0, hi - lo)
    vix[lo:hi] += np.linspace(0, 30.0, hi - lo)
    hy = np.clip(hy, 2.0, None)
    return pd.DataFrame({"hy": hy, "ig": hy * 0.35, "vix": np.clip(vix, 9.0, None)}, index=idx)


def test_score_is_bounded_unit_interval():
    frame = _synthetic_frame()
    state = mc.risk_off_state(frame.index, frame=frame)
    score = state["score"].dropna()
    assert len(score) > 0
    assert score.min() >= 0.0 and score.max() <= 1.0
    # the injected risk-off episode must actually pull the score down somewhere (signal has bite)
    assert score.min() < 0.5


def test_score_is_causal_shocking_a_late_date_leaves_earlier_scores_unchanged():
    frame = _synthetic_frame()
    base = mc.risk_off_state(frame.index, frame=frame)["score"]

    shocked = frame.copy()
    shock_at = int(len(frame) * 0.9)
    shocked.iloc[shock_at:, shocked.columns.get_loc("hy")] += 10.0     # huge late HY blowout
    shocked.iloc[shock_at:, shocked.columns.get_loc("vix")] += 50.0
    after = mc.risk_off_state(shocked.index, frame=shocked)["score"]

    # every score strictly before the shock date is identical — no look-ahead leakage backwards
    early = base.index[:shock_at]
    pd.testing.assert_series_equal(base.loc[early], after.loc[early])
    # and the shock DID change something at/after the shock (otherwise the test is vacuous)
    assert not base.loc[base.index[shock_at:]].equals(after.loc[after.index[shock_at:]])


def test_score_shifted_one_day_relative_to_raw():
    """The traded score is the raw score shifted one day (causal). First traded value is NaN."""
    frame = _synthetic_frame()
    state = mc.risk_off_state(frame.index, frame=frame)
    assert np.isnan(state["score"].iloc[0])
    pd.testing.assert_series_equal(
        state["score"].iloc[1:], state["raw_score"].shift(1).iloc[1:])


def test_calm_regime_scores_near_full_risk_on():
    """With flat spreads and low vol, risk appetite should sit high (near full exposure)."""
    n = 700
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    frame = pd.DataFrame({"hy": np.full(n, 3.0), "ig": np.full(n, 1.0),
                          "vix": np.full(n, 15.0)}, index=idx)
    score = mc.risk_off_state(frame.index, frame=frame)["score"].dropna()
    assert score.mean() > 0.8
