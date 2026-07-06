import numpy as np

from mds import backtest
from mds.statarb import hysteresis_signal


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
