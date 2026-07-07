import numpy as np

from mds import backtest
from mds.statarb import hysteresis_signal, walk_forward_backtest


def test_positive_edge_gives_positive_sharpe():
    rng = np.random.default_rng(0)
    returns = 0.001 + rng.normal(scale=0.005, size=2000)
    position = np.ones(2000)
    r = backtest.run(returns, position, cost_bps=0.0, periods_per_year=252)
    assert r["sharpe"] > 0
    assert r["total_return"] > 0


def test_costs_reduce_performance():
    rng = np.random.default_rng(1)
    returns = rng.normal(scale=0.01, size=1000)
    position = np.where(np.arange(1000) % 2 == 0, 1.0, -1.0)  # flips every period → high turnover
    free = backtest.run(returns, position, cost_bps=0.0, periods_per_year=252)
    costly = backtest.run(returns, position, cost_bps=50.0, periods_per_year=252)
    assert costly["total_return"] < free["total_return"]
    assert costly["num_trades"] > 0


def test_execution_lag_prevents_lookahead():
    # A position taken on the final period cannot earn that period's return.
    returns = np.array([0.0, 0.0, 0.0, 0.10])
    position = np.array([0.0, 0.0, 0.0, 1.0])
    r = backtest.run(returns, position, cost_bps=0.0, periods_per_year=252)
    assert abs(r["total_return"]) < 1e-9


def test_hysteresis_signal_enters_and_exits():
    z = np.array([0.0, 3.0, 1.0, 0.2, -3.0, 0.0])
    pos = hysteresis_signal(z, entry=2.0, exit=0.5)
    np.testing.assert_array_equal(pos, [0.0, -1.0, -1.0, 0.0, 1.0, 0.0])


def test_walk_forward_is_out_of_sample_and_scores_the_right_span():
    # A genuinely cointegrated pair (random-walk x, strongly mean-reverting stationary spread).
    # The walk-forward backtest re-fits beta on trailing data and trades the reverting spread
    # out-of-sample, so it should be tradeable (clearly positive Sharpe) and score exactly the
    # bars after the first lookback window.
    rng = np.random.default_rng(7)
    n, lookback, step = 3000, 480, 48
    x = np.cumsum(rng.normal(0, 0.01, n)) + 10.0
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = 0.9 * s[t - 1] + rng.normal(0, 0.01)  # AR(1) mean-reverting spread
    y = 0.8 * x + s
    bt = walk_forward_backtest(y, x, window=48, entry=2.0, exit=0.5, cost_bps=0.0,
                               ppy=8760, lookback=lookback, step=step)
    assert bt["oos_observations"] == n - lookback
    assert bt["sharpe"] > 2.0  # OOS-tradeable when the pair really is cointegrated


def test_walk_forward_has_no_lookahead():
    # Deterministic no-look-ahead proof: perturbing only the TAIL (bars >= K) must leave every
    # out-of-sample return BEFORE K unchanged — sizing at each bar depends solely on trailing data.
    rng = np.random.default_rng(1)
    n, lookback, K = 3000, 480, 2000
    x = np.cumsum(rng.normal(0, 0.01, n)) + 10.0
    y = 0.8 * x + rng.normal(0, 0.02, n)
    base = walk_forward_backtest(y, x, 48, 2.0, 0.5, 0.0, 8760, lookback, 48)["net_returns"]
    y2 = y.copy()
    y2[K:] += 5.0
    perturbed = walk_forward_backtest(y2, x, 48, 2.0, 0.5, 0.0, 8760, lookback, 48)["net_returns"]
    np.testing.assert_allclose(base[:K - lookback], perturbed[:K - lookback])
    assert not np.allclose(base, perturbed)  # the tail itself did change
