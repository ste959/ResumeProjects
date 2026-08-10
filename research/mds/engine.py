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
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from . import evaluation as ev
from . import execution as ex

TRADING_DAYS = 252


@dataclass
class BacktestConfig:
    """Execution assumptions applied uniformly to every strategy (so comparisons are apples-to-apples)."""
    rebalance: int = 21           # trading days between re-weights
    cost_bps: float = 10.0        # flat turnover cost (bps) — used when `execution` is None
    max_leverage: float = 3.0     # gross-exposure cap (long-only strategies never bind it)
    rf: pd.Series | None = None   # daily risk-free return; Sharpes are measured in excess of it
    execution: ex.ExecutionModel | None = None   # None → FlatBps(cost_bps); set to RealisticExecution for realism
    aum: float = 1e8              # portfolio capital ($) — turns weights into notional for impact/capacity


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


def run(strategy: Strategy, prices: pd.DataFrame, config: BacktestConfig | None = None,
        liquidity: ex.Liquidity | None = None) -> StrategyResult:
    """Walk-forward backtest of one strategy through the shared engine. Costs come from `config.execution`
    (defaults to a flat-bps model); pass `liquidity` when using `RealisticExecution` so spread/impact/
    participation are priced off real ADV, vol, and spread."""
    cfg = config or BacktestConfig()
    exec_model = cfg.execution or ex.FlatBps(cfg.cost_bps)
    syms = strategy.symbols()
    px = prices[syms].dropna()
    rets = px.pct_change()
    strategy.prepare(px)

    # Align liquidity panels to this run's dates/symbols (only needed by realistic execution).
    adv = vol = spr = None
    if liquidity is not None:
        adv = liquidity.adv_usd.reindex(index=rets.index, columns=syms)
        vol = liquidity.daily_vol.reindex(index=rets.index, columns=syms)
        spr = liquidity.spread_frac.reindex(index=rets.index, columns=syms)

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
        liq = None
        if liquidity is not None:
            liq = {"adv": adv.iloc[t - 1].to_numpy(), "vol": vol.iloc[t - 1].to_numpy(),
                   "spread": spr.iloc[t - 1].to_numpy()}
        w_ach, cost = exec_model.rebalance(w_prev, w, cfg.aum, liq)   # partial fills → achieved ≠ target
        block = rets.iloc[t:t + cfg.rebalance].to_numpy()
        port = block @ w_ach - exec_model.carry(w_ach, days=1)        # daily borrow/financing drag
        if len(port):
            port[0] -= cost                                   # one-off spread + impact on the rebalance day
            net.iloc[t:t + len(port)] = port
            W.iloc[t:t + len(port)] = w_ach
        grosses.append(float(np.abs(w_ach).sum()))
        turns.append(float(np.abs(w_ach - w_prev).sum()))
        w_prev = w_ach

    net, W = net.iloc[start:], W.iloc[start:]
    return StrategyResult(
        name=strategy.name, net=net, weights=W, stats=ev.stats(net, cfg.rf),
        avg_gross=round(float(np.mean(grosses)), 2) if grosses else 0.0,
        turnover_ann=round(float(np.mean(turns)) * (TRADING_DAYS / cfg.rebalance), 1) if turns else 0.0)


def capacity_curve(strategy: Strategy, prices: pd.DataFrame, liquidity: ex.Liquidity,
                   aums: list[float], base: BacktestConfig | None = None) -> list[dict]:
    """Run the SAME strategy at increasing AUM under realistic execution — the answer to 'does the edge
    survive size?'. As capital grows, trades become a larger share of ADV, so spread+impact+partial-fill
    costs rise and the net Sharpe decays. Capacity is part of whether an alpha is real."""
    cfg = base or BacktestConfig()
    out = []
    for aum in aums:
        r = run(strategy, prices, replace(cfg, aum=aum, execution=ex.RealisticExecution()), liquidity)
        out.append({"aum": aum, "sharpe": r.stats["sharpe"], "ann_return": r.stats["ann_return"],
                    "turnover_ann": r.turnover_ann, "avg_gross": r.avg_gross})
    return out


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
