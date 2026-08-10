"""The strategy engine — one interface, one walk-forward loop, one honest measuring stick.

Every study in this repo (allocation, trend, factor) was its own bespoke backtest. This module is the
**platform spine**: a researcher expresses a strategy once — a `symbols()` list and a causal
`target_weights(prices, t)` — and gets the *same* walk-forward execution (one-day lag, turnover cost,
leverage cap), the *same* evaluation (`evaluation.py`: excess-of-cash Sharpe, HAC t, bootstrap CI, tail
metrics), the *same* selection-aware gauntlet across strategies, and a standardized tearsheet + P&L
attribution — for free.

The contract that keeps it honest: `target_weights(prices, t)` may use **only** `prices.iloc[:t]` (data
through the prior close); the engine earns those weights on `t → t+rebalance`. No look-ahead is possible
by construction, and a test asserts it. Pure NumPy/pandas — no I/O; `run_lab.py` feeds it real data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import evaluation as ev

TRADING_DAYS = 252


@dataclass
class BacktestConfig:
    """Execution assumptions applied uniformly to every strategy (so comparisons are apples-to-apples)."""
    rebalance: int = 21           # trading days between re-weights
    cost_bps: float = 10.0        # turnover cost, one-way, in basis points
    max_leverage: float = 3.0     # gross-exposure cap (long-only strategies never bind it)
    rf: pd.Series | None = None   # daily risk-free return; Sharpes are measured in excess of it


class Strategy(ABC):
    """Subclass this and implement `symbols()` + `target_weights()`. Optionally override `prepare()` to
    precompute causal signal panels once, and `warmup` (bars of history needed before the first trade)."""
    name: str = "strategy"
    warmup: int = 252

    @abstractmethod
    def symbols(self) -> list[str]:
        """The tickers this strategy trades (a subset of the columns of the price panel)."""

    def prepare(self, prices: pd.DataFrame) -> None:
        """Optional: precompute anything causal once (e.g. a rolling signal panel) before the loop."""

    @abstractmethod
    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        """Target weights over `symbols()`, using ONLY `prices.iloc[:t]` (through the prior close). May
        be long-only (sum to 1) or long/short (the engine caps gross at `max_leverage`)."""


@dataclass
class StrategyResult:
    """Everything one backtest produces: the net series, the held-weights panel (for attribution), the
    honest stat block, and activity diagnostics."""
    name: str
    net: pd.Series
    weights: pd.DataFrame
    stats: dict
    avg_gross: float
    turnover_ann: float


def run(strategy: Strategy, prices: pd.DataFrame, config: BacktestConfig | None = None) -> StrategyResult:
    """Walk-forward backtest of one strategy through the shared engine."""
    cfg = config or BacktestConfig()
    syms = strategy.symbols()
    px = prices[syms].dropna()
    rets = px.pct_change()
    strategy.prepare(px)

    n = len(syms)
    net = pd.Series(0.0, index=rets.index)
    W = pd.DataFrame(0.0, index=rets.index, columns=syms)
    w_prev = np.zeros(n)
    grosses, turns = [], []
    start = max(strategy.warmup, 1)

    for t in range(start, len(rets), cfg.rebalance):
        w = np.nan_to_num(np.asarray(strategy.target_weights(px, t), dtype=float))   # causal: uses px[:t]
        g = float(np.abs(w).sum())
        if g > cfg.max_leverage:
            w = w * (cfg.max_leverage / g)                    # honest gross-leverage cap
        block = rets.iloc[t:t + cfg.rebalance].to_numpy()
        port = block @ w
        turn = float(np.abs(w - w_prev).sum())
        if len(port):
            port[0] -= turn * cfg.cost_bps / 1e4              # charge turnover on the rebalance day
            net.iloc[t:t + len(port)] = port
            W.iloc[t:t + len(port)] = w
        grosses.append(float(np.abs(w).sum()))
        turns.append(turn)
        w_prev = w

    net, W = net.iloc[start:], W.iloc[start:]
    return StrategyResult(
        name=strategy.name, net=net, weights=W, stats=ev.stats(net, cfg.rf),
        avg_gross=round(float(np.mean(grosses)), 2) if grosses else 0.0,
        turnover_ann=round(float(np.mean(turns)) * (TRADING_DAYS / cfg.rebalance), 1) if turns else 0.0)


def compare(strategies: list[Strategy], prices: pd.DataFrame,
            config: BacktestConfig | None = None) -> dict:
    """Run several strategies through the identical engine and judge them as a SET with the selection-
    aware gauntlet — because comparing N strategies on one history IS multiple testing."""
    cfg = config or BacktestConfig()
    results = [run(s, prices, cfg) for s in strategies]
    gauntlet = ev.gauntlet({r.name: r.net for r in results}, cfg.rf)
    return {"results": results, "gauntlet": gauntlet}


def attribution(result: StrategyResult, prices: pd.DataFrame, groups: dict | None = None) -> dict:
    """Decompose net return into each asset's daily contribution (wᵢ·rᵢ); optionally roll up to groups
    (e.g. asset-class sleeves). Contributions reconcile to the gross-of-cost net return."""
    rets = prices[result.weights.columns].pct_change().reindex(result.weights.index)
    per_asset = (rets * result.weights).sum()
    out = {"per_asset": per_asset.sort_values(ascending=False),
           "net_exposure": result.weights.mean(), "gross_exposure": result.weights.abs().mean()}
    if groups:
        key = lambda a: groups.get(a, "Other")
        out["per_group"] = per_asset.groupby(key).sum().sort_values(ascending=False)
        out["net_by_group"] = result.weights.mean().groupby(key).sum()
    return out


def tearsheet(result: StrategyResult) -> dict:
    """The standardized performance report for any strategy — the trader/researcher-facing summary."""
    s = result.stats
    return {
        "name": result.name,
        "performance": {"ann_return": s["ann_return"], "ann_vol": s["ann_vol"], "sharpe": s["sharpe"],
                        "hac_t": s["hac_t"], "sharpe_ci": (s["boot_lo"], s["boot_hi"]),
                        "max_drawdown": s["max_drawdown"]},
        "tail": {"sortino": s["sortino"], "calmar": s["calmar"], "cvar_5": s["cvar_5"], "skew": s["skew"]},
        "activity": {"avg_gross": result.avg_gross, "turnover_ann": result.turnover_ann,
                     "n_days": s["n_days"]},
    }


def print_tearsheet(result: StrategyResult) -> None:
    """Pretty-print a tearsheet to the terminal."""
    ts = tearsheet(result)
    p, tl, a = ts["performance"], ts["tail"], ts["activity"]
    print(f"── {ts['name']} " + "─" * max(0, 58 - len(ts['name'])))
    print(f"   return {p['ann_return']*100:>6.1f}%   vol {p['ann_vol']*100:>5.1f}%   "
          f"exSharpe {p['sharpe']:>5.2f} (HAC t {p['hac_t']:+.1f}, CI [{p['sharpe_ci'][0]:.2f},{p['sharpe_ci'][1]:.2f}])")
    print(f"   maxDD {p['max_drawdown']*100:>6.1f}%   Sortino {tl['sortino']:>5.2f}   "
          f"Calmar {tl['calmar']:>5.2f}   CVaR5 {tl['cvar_5']*100:>5.2f}%   skew {tl['skew']:+.2f}")
    print(f"   gross {a['avg_gross']:.2f}x   turnover ~{a['turnover_ann']:.0f}x/yr   {a['n_days']} days")
