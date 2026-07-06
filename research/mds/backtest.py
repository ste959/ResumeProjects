"""A small, honest vectorized backtester.

Deliberately conservative: it charges transaction costs on every change in position and
applies the position with a one-period lag (the signal at t is only tradable at t+1), so
there is no look-ahead. The metrics are the ones that actually matter for judging a
signal — Sharpe, drawdown, turnover, hit rate — not just the equity curve.
"""

from __future__ import annotations

import numpy as np


def run(returns: np.ndarray, position: np.ndarray, cost_bps: float = 1.0,
        periods_per_year: float = 24 * 365) -> dict:
    """Backtest a position series against per-period returns of the traded instrument.

    `position[t]` is the desired position decided using information up to t; it earns
    `returns[t+1]`. Costs are charged on |Δposition| each period.
    """
    returns = np.asarray(returns, dtype=float)
    position = np.asarray(position, dtype=float)
    position = np.nan_to_num(position)

    # One-period lag: yesterday's position earns today's return.
    held = np.roll(position, 1)
    held[0] = 0.0
    gross = held * returns

    turnover = np.abs(np.diff(np.concatenate([[0.0], position])))
    costs = turnover * (cost_bps / 1e4)
    net = gross - costs

    equity = np.cumprod(1.0 + net)
    return {
        "net_returns": net,
        "equity": equity,
        **metrics(net, position, periods_per_year),
    }


def metrics(net: np.ndarray, position: np.ndarray, periods_per_year: float) -> dict:
    net = np.asarray(net, dtype=float)
    equity = np.cumprod(1.0 + net)
    ann_return = equity[-1] ** (periods_per_year / max(len(net), 1)) - 1.0 if len(net) else 0.0
    vol = net.std(ddof=0)
    sharpe = (net.mean() / vol * np.sqrt(periods_per_year)) if vol > 0 else 0.0

    peak = np.maximum.accumulate(equity)
    max_dd = float((equity / peak - 1.0).min()) if len(equity) else 0.0

    active = position != 0
    traded = net[np.roll(active, 1)]
    hit = float((traded > 0).mean()) if traded.size else 0.0
    trades = int((np.diff(np.concatenate([[0.0], position])) != 0).sum())

    return {
        "sharpe": float(sharpe),
        "ann_return": float(ann_return),
        "total_return": float(equity[-1] - 1.0) if len(equity) else 0.0,
        "max_drawdown": max_dd,
        "hit_rate": hit,
        "num_trades": trades,
        "periods": int(len(net)),
    }
