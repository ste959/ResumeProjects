# Risk & TCA Note
### The risk system a live book runs on, and the paper-vs-reality ledger

*Platform sprint 3 · risk analytics + implementation shortfall · ts-momentum book · realistic execution · $500M*

---

## Why this exists

A backtest Sharpe says nothing about *how much you can lose*, *where the risk lives*, *what a crisis does
to today's positioning*, or *how much of the paper P&L survives execution*. Those are the questions a desk
actually asks before and while a strategy is live. This sprint adds the four answers, all operating on any
`engine.StrategyResult`.

## [1] Risk report (`mds/riskmgmt.py`)

On the live trend book:

| Measure | Value |
|---|--:|
| Realized vol | 9.5%/yr |
| Ex-ante vol (current weights × Σ) | 15.8%/yr |
| VaR 95% (historical) | 0.99%/day |
| VaR 95% (Cornish–Fisher, fat-tail-adjusted) | 1.03%/day |
| VaR 99% | 1.69%/day |
| Expected shortfall (CVaR 95%) | 1.47%/day |
| **Risk contribution by sleeve** | **Equity +78%, Credit +23%**, Commodity/Rates/USD ≈ 0 |

Two things a single Sharpe hides: **Cornish–Fisher VaR exceeds the Gaussian** because returns are
fat-tailed (the honest tail is worse than a normal says), and the **marginal risk contributions** show the
book's risk is ~three-quarters *equity* even though it holds 13 markets — concentration a headline vol
number can't see.

## [2] Stress test — the current book replayed through historical shocks

| Scenario | Book return | Worst day |
|---|--:|--:|
| **2022 rate shock** (stocks + bonds) | **−21.9%** | −5.0% |
| Mar-2023 banking (SVB/CS) | +1.0% | −2.0% |
| Aug-2024 vol spike | −0.3% | −2.6% |
| Apr-2025 tariff selloff | −1.8% | −4.6% |

This applies *today's* weights to each crisis window — "what would the book I hold now have done then." The
2022 replay is the sobering one: the current long-tilted book would have lost ~22% in that regime. Regular
performance stats never ask that of the current positioning; stress testing does.

## [3] Limit checks — the book vs. its mandate

| Limit | Value | Cap | |
|---|--:|--:|:--|
| **max name weight** | **0.66** | 0.60 | **BREACH** |
| max sleeve weight | 0.85 | 0.90 | ok |
| max gross | 2.27 | 2.50 | ok |
| max ann vol | 0.095 | 0.25 | ok |
| max VaR 95% | 0.010 | 0.05 | ok |

The single-name limit **catches a real breach** — one position exceeds 60% of the book. This is the gate a
desk runs continuously; a strategy that backtests well but violates the mandate isn't deployable.

## [4] Implementation shortfall / TCA (`mds/tca.py`)

Perold's decomposition, computed by running the *same* strategy three ways (ideal / cost-only / realistic)
and differencing. Annualized:

| AUM | Ideal ret | Real ret | Execution cost | Opportunity cost | Total shortfall |
|---|--:|--:|--:|--:|--:|
| $100M | +4.4% | +2.5% | 3.12% | −1.26% | **1.87%** |
| $500M | +4.4% | +2.1% | 4.57% | −2.28% | **2.29%** |
| $2B | +4.4% | +4.2% | 7.18% | −7.04% | **0.15%** |

Read it carefully — this is the interesting part:
- **Execution cost rises with size** (3.1% → 7.2%): bigger orders pay more spread + impact, and the
  short/leverage **borrow-and-financing carry** (~1.5%/yr on a 2×-gross long/short book) is a large,
  fixed piece most backtests omit entirely.
- **Opportunity cost is *negative* and grows** (−1.3% → −7.0%): at size, the participation cap *prevents*
  the most expensive trades from filling — and here those unfilled trades would mostly have *lost* money,
  so not filling them *helped*. The cap acts as an accidental brake.
- The two effects nearly cancel at $2B, but that's coincidence, not comfort: the book at that size is
  barely trading (a third of target gross, per the [capacity curve](EXECUTION-NOTE.md)).

The lesson: **paper P&L and real P&L are different animals**, and the difference has a structure —
what you *paid* to trade vs. what you *couldn't* trade. A strategy isn't real until that ledger is small
enough at your intended size.

## What this demonstrates

- **A working risk system, not just metrics.** VaR/ES with a fat-tail correction, risk *attribution*
  (where the risk lives), scenario replay of the *current* book, and mandate enforcement — the pieces a
  desk runs, each on the same `StrategyResult`.
- **TCA that ties the platform together.** Implementation shortfall reuses sprint-2's execution model and
  the engine; no new backtest, just orchestration — and it turns "the backtest said 4.4%" into "you'd keep
  2.1% at $500M, and here's exactly where the other 2.3% went."

Reproduce with `python run_risk.py` (see [`REPRODUCE.md`](REPRODUCE.md)); the analytics are pure and
unit-tested in `tests/test_riskmgmt.py` and `tests/test_tca.py`.
