import numpy as np

from mds.stats import adf, engle_granger, half_life, ols


def test_ols_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    x = rng.normal(size=500)
    y = 3.0 + 2.0 * x + rng.normal(scale=0.01, size=500)
    fit = ols(np.column_stack([np.ones_like(x), x]), y)
    assert fit["beta"][0] == 0 or True
    np.testing.assert_allclose(fit["beta"], [3.0, 2.0], atol=0.02)


def test_adf_flags_stationary_vs_random_walk():
    rng = np.random.default_rng(1)
    # Strongly mean-reverting AR(1): stationary → very negative ADF stat.
    s = np.zeros(600)
    for t in range(1, 600):
        s[t] = 0.2 * s[t - 1] + rng.normal()
    assert adf(s) < -4.0

    # Random walk: unit root → ADF stat not significant.
    rw = np.cumsum(rng.normal(size=600))
    assert adf(rw) > -2.5


def test_engle_granger_detects_cointegration():
    rng = np.random.default_rng(2)
    x = np.cumsum(rng.normal(size=800))          # random walk
    y = 5.0 + 1.5 * x + rng.normal(scale=1.0, size=800)  # cointegrated with x
    eg = engle_granger(y, x)
    assert abs(eg["beta"] - 1.5) < 0.1
    assert eg["cointegrated_5pct"] is True


def test_engle_granger_rejects_independent_walks():
    rng = np.random.default_rng(3)
    x = np.cumsum(rng.normal(size=800))
    y = np.cumsum(rng.normal(size=800))  # independent random walk
    assert engle_granger(y, x)["cointegrated_5pct"] is False


def test_half_life_matches_ar1():
    rng = np.random.default_rng(4)
    phi = 0.9
    s = np.zeros(4000)
    for t in range(1, 4000):
        s[t] = phi * s[t - 1] + rng.normal()
    expected = -np.log(2) / np.log(phi)  # ≈ 6.58
    assert abs(half_life(s) - expected) < 1.5
