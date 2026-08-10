# The Quant Platform — from concept to execution to risk

**One system for the whole life of a strategy:** form a hypothesis, research a signal, backtest it under
realistic conditions, put it through an overfitting-aware validation gauntlet, size it under risk, and
carry it to paper/live execution — then attribute and monitor what it does. The formerly-separate studies
in `mds/` are now components of a single pipeline behind one **Strategy SDK**.

> This is the finance flagship of the repo. The crypto matching engine (`/exchange`) and fixed-income
> desk (`/oms`) are **systems/SWE** showcases (matching-engine throughput, event-driven architecture);
> the microstructure/LOB work from the exchange also feeds this platform's execution-realism layer.

## The pipeline

```
  Data              Signal            Backtest           Validation        Risk & Execution     Report
  ─────             ──────            ────────           ──────────        ────────────────     ──────
  Alpaca / FRED  →  factors,       →  walk-forward,   →  Deflated Sharpe,  →  factor risk,     →  tearsheet,
  EDGAR, cache      trend, carry,     cost & lag,        PBO, HAC t,          vol-target,          P&L & factor
  (point-in-time)   cross-section     leverage cap       bootstrap CI         paper (Alpaca)       attribution
```

Every stage is shared. A strategy plugs into it once and inherits all of it.

## The Strategy SDK

A researcher expresses a strategy as a `symbols()` list and a **causal** `target_weights(prices, t)` —
and gets the entire pipeline for free. The contract that guarantees no look-ahead: `target_weights` may
read only `prices.iloc[:t]` (through the prior close); the engine earns those weights on `t → t+1`.

```python
from mds.engine import Strategy, run, compare, print_tearsheet

class MyIdea(Strategy):
    name = "my-idea"
    warmup = 252
    def symbols(self):
        return ["SPY", "IEF", "GLD", "DBC"]
    def target_weights(self, prices, t):
        window = prices.iloc[t-252:t]                 # causal — only the past
        signal = window.pct_change().mean()           # (your alpha here)
        w = signal / signal.abs().sum()
        return w.to_numpy()

result = run(MyIdea(), prices, BacktestConfig(cost_bps=10, rf=rf))
print_tearsheet(result)                               # standardized performance report
```

That's the whole integration. The engine supplies:

- **Walk-forward execution** — one-day lag, turnover cost, gross-leverage cap, held-weights recorded.
- **Honest evaluation** (`evaluation.py`) — excess-of-cash Sharpe, Newey–West t-stat, block-bootstrap CI,
  drawdown, and downside/tail metrics (Sortino, Calmar, CVaR, skew).
- **Selection-aware gauntlet** — run N strategies through `compare()` and they're judged as a *set*
  (Deflated Sharpe, PBO, the multiple-testing t-bar, min-detectable-Sharpe power) — because comparing
  strategies on one history *is* multiple testing.
- **Attribution** — per-asset and per-sleeve P&L, net/gross exposure, turnover.
- **Tearsheet** — one standardized report for any strategy.

`run_lab.py` runs five strategies (equal-weight, 60/40, risk parity, min-variance, trend) — allocation,
benchmark, and long/short — through the *identical* engine and gauntlet, then prints a comparison and a
tearsheet. Adding a sixth is a subclass.

## What's built vs. the roadmap

**Built (this sprint + the existing studies):**
- The Strategy SDK + engine + shared evaluation/gauntlet + attribution + tearsheet (`engine.py`,
  `strategies_lib.py`, `run_lab.py`).
- A deep validation stack (`validation.py`): Deflated Sharpe, PBO/CSCV, Newey–West, block bootstrap,
  min-detectable-Sharpe power — the platform's differentiator.
- Strategy families as components: cross-sectional factors, portfolio construction (risk model, timing,
  options, tax), multi-asset allocation, and an ablation-and-diagnostics trend study.

**Roadmap (the sprints that make it a *production* research desk):**
1. **Execution & cost realism** — replace flat-bps with spread/slippage, square-root **market impact**,
   short **borrow** cost, partial fills and participation caps (optionally backed by the exchange's LOB
   engine). This is what makes "alpha under *real* conditions" a claim, not a hope.
2. **Data integrity** — point-in-time, **survivorship-free** universe (today's equity backtests are
   optimistic; this is the biggest data hole, disclosed in [`ALPHA-DATA-ROADMAP.md`](ALPHA-DATA-ROADMAP.md)).
3. **Risk & execution loop** — live exposures, VaR/CVaR, **stress/scenario replay**, limit checks; and a
   paper-trade → **implementation-shortfall (TCA)** loop that measures whether live fills match the
   backtest's assumptions.
4. **Tooling** — strategy registry/leaderboard and a richer tearsheet (rolling Sharpe, factor-exposure
   time series).

## Why this design

- **For a researcher:** rigor is not optional — every strategy is measured on the same excess-of-cash,
  overfitting-corrected stick, so a pretty backtest can't hide from the gauntlet.
- **For an engineer:** it's a clean plugin architecture — an abstract base class, a pure engine, a shared
  evaluation module, and a test suite that asserts the no-look-ahead contract. New strategies compose;
  they don't fork the backtester.

Run it: `python run_lab.py`. Tests: `python -m pytest tests/test_engine.py` (the engine contract) and the
full suite (`python -m pytest`).
