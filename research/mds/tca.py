"""Transaction-cost analysis — implementation shortfall (Perold 1988).

The gap between a strategy on paper and the same strategy after it touches the market has a name and a
decomposition. Here it's computed by running the *same* strategy through the engine three ways and
differencing:

  1. **ideal**      — frictionless, full fills (the paper portfolio: what the signal *wanted*).
  2. **cost-only**  — realistic spread + impact + borrow, but fills are unconstrained (isolates the cost
                      of *trading*, holding fills fixed).
  3. **realistic**  — the full model, including the participation cap → partial fills.

From these:
  • **execution cost**   = ideal − cost-only   (spread + impact + financing you paid to trade)
  • **opportunity cost** = cost-only − realistic (P&L foregone on the shares you *couldn't* fill)
  • **total shortfall**  = ideal − realistic     (the whole gap between paper and reality)

The one-day execution lag is held constant across all three, so it cancels (it's not separated here).
Reuses the engine and `RealisticExecution` from sprints 1–2 — no new backtest. Pure orchestration.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from . import engine as eng
from . import execution as ex

TRADING_DAYS = 252


def _ann_return(net: pd.Series) -> float:
    """Annualized (arithmetic) mean return — the basis for attributing cost components additively."""
    return float(net.mean() * TRADING_DAYS)


def implementation_shortfall(strategy: eng.Strategy, prices: pd.DataFrame, liquidity: ex.Liquidity,
                             config: eng.BacktestConfig | None = None, aum: float = 5e8) -> dict:
    """Decompose the paper-vs-reality gap for one strategy at a given AUM. Returns the three runs' Sharpes
    and the execution / opportunity / total shortfall as annualized return drags (fractions)."""
    cfg = config or eng.BacktestConfig()
    ideal = eng.run(strategy, prices, replace(cfg, execution=ex.FlatBps(0.0), aum=aum))
    cost_only = eng.run(strategy, prices,
                        replace(cfg, execution=ex.RealisticExecution(max_participation=1e12), aum=aum), liquidity)
    realistic = eng.run(strategy, prices,
                        replace(cfg, execution=ex.RealisticExecution(), aum=aum), liquidity)

    exec_cost = _ann_return(ideal.net) - _ann_return(cost_only.net)
    opportunity_cost = _ann_return(cost_only.net) - _ann_return(realistic.net)
    total = _ann_return(ideal.net) - _ann_return(realistic.net)
    return {
        "aum": aum,
        "ideal_sharpe": ideal.stats["sharpe"], "realistic_sharpe": realistic.stats["sharpe"],
        "ideal_ann_return": round(_ann_return(ideal.net), 4),
        "realistic_ann_return": round(_ann_return(realistic.net), 4),
        "execution_cost_annual": round(exec_cost, 4),
        "opportunity_cost_annual": round(opportunity_cost, 4),
        "total_shortfall_annual": round(total, 4),
        "realistic_avg_gross": realistic.avg_gross,
    }
