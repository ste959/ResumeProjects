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
  Alpaca / FRED  →  factors,       →  walk-forward,   →  Deflated Sharpe,  →  VaR/ES, stress,  →  tearsheet,
  EDGAR, cache      trend, carry,     spread+impact,     PBO, HAC t,          limits, TCA,         P&L & factor
  (point-in-time)   cross-section     borrow, capacity   bootstrap CI         paper (Alpaca)       attribution
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

**Built (sprints 1–3 + the existing studies):**
- The Strategy SDK + engine + shared evaluation/gauntlet + attribution + tearsheet (`engine.py`,
  `strategies_lib.py`, `run_lab.py`).
- **Execution & cost realism** (`execution.py`, `run_execution.py`) — half-spread (ADV-tier or
  Corwin–Schultz), **square-root market impact**, a **participation cap with partial fills**, and
  short-**borrow**/financing carry; plus a **capacity curve** that sweeps AUM to find where the edge
  decays. See [`EXECUTION-NOTE.md`](EXECUTION-NOTE.md).
- **Risk system + TCA** (`riskmgmt.py`, `tca.py`, `run_risk.py`) — VaR / expected shortfall (with a
  Cornish–Fisher fat-tail correction), **risk-contribution attribution** (where the risk lives),
  **stress/scenario replay** of the current book, **limit checks** vs. a mandate, and an
  **implementation-shortfall** ledger (execution vs. opportunity cost). See [`RISK-NOTE.md`](RISK-NOTE.md).
- A deep validation stack (`validation.py`): Deflated Sharpe, PBO/CSCV, Newey–West, block bootstrap,
  min-detectable-Sharpe power — the platform's differentiator.
- Strategy families as components: cross-sectional factors, portfolio construction (risk model, timing,
  options, tax), multi-asset allocation, and an ablation-and-diagnostics trend study.

**Roadmap (the sprints that make it a *production* research desk):**
1. **Data integrity** — point-in-time, **survivorship-free** universe (today's equity backtests are
   optimistic; this is the biggest data hole, disclosed in [`ALPHA-DATA-ROADMAP.md`](ALPHA-DATA-ROADMAP.md)).
2. **Live TCA loop** — extend the implementation-shortfall ledger to *actual* paper-trade fills from the
   live Alpaca engine, so modeled cost is checked against realized cost.
3. **Tooling** — strategy registry/leaderboard and a richer tearsheet (rolling Sharpe, factor-exposure
   time series).
4. **LOB-backed fills** — plug the exchange's order-book engine in as the fill model for the highest-
   fidelity impact simulation (collapsing app #1 into the platform).

## Why this design

- **For a researcher:** rigor is not optional — every strategy is measured on the same excess-of-cash,
  overfitting-corrected stick, so a pretty backtest can't hide from the gauntlet.
- **For an engineer:** it's a clean plugin architecture — an abstract base class, a pure engine, a shared
  evaluation module, and a test suite that asserts the no-look-ahead contract. New strategies compose;
  they don't fork the backtester.

Run it: `python run_lab.py`. Tests: `python -m pytest tests/test_engine.py` (the engine contract) and the
full suite (`python -m pytest`).
