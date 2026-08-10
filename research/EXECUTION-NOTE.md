# Execution & Capacity Note
### From "backtest Sharpe" to "alpha under real conditions"

*Platform sprint 2 · realistic cost model + capacity curve · 13 ETF markets · 2020-07 – 2026-07*

---

## Why this exists

A flat "10 bps" cost is the single biggest lie in most backtests. It ignores the two things that actually
decide whether an edge survives: **the spread you cross** and **the impact you cause** — both of which
scale with **how much money you run** versus how much the asset trades. This sprint replaces the flat
cost with a model that prices all of it, so the platform can answer *"is this alpha under real
conditions, and up to what size?"* rather than *"is this alpha in a frictionless world?"*

## The model (`mds/execution.py`)

| Component | How it's modeled |
|---|---|
| **Bid–ask spread** | Half-spread paid on every trade. Default: an **ADV-tier** proxy (spread ↓ as dollar volume ↑, calibrated so a ~$30B-ADV ETF is sub-bp, a ~$200M name ~6 bps). **Corwin–Schultz (2012)** high/low estimator is also implemented as a cross-check. |
| **Market impact** | The **square-root law** (Almgren): `impact ≈ coef · σ · √(traded / ADV)`. Big trades in thin names move the price against you. |
| **Participation cap + partial fills** | You can trade at most a fraction of a day's volume per rebalance; the shortfall **doesn't fill** and carries forward. This is what makes the backtest **capacity-aware**. |
| **Short borrow & financing** | Short legs pay borrow (bps/yr on short notional); leverage pays financing (bps/yr on gross above 1×) — charged daily. The carry a long/short book actually bears. |

An honest note on the spread: **Corwin–Schultz overestimates for liquid names** (it reads intraday
volatility as spread — it put SPY at ~36 bps vs. a real sub-bp), so the ADV-tier model is the default and
CS is kept as a documented cross-check. True spreads need intraday quote data.

## Flat vs. realistic (AUM $100M, excess of cash)

| Strategy | Flat 10 bps | Realistic | Δ |
|---|--:|--:|--:|
| risk-parity | 0.32 | 0.18 | −0.15 |
| ts-momentum | −0.08 | −0.10 | −0.02 |

The flat model **flatters** the picture: low-turnover risk parity loses 0.15 of Sharpe to real spread,
and once you price impact and borrow, the ranking and magnitudes shift. Realistic costs are not a
rounding error.

## The capacity curve — does the edge survive size?

The trend book (highest turnover, trades the thinner sleeves) under realistic execution, swept over AUM:

| AUM | Excess Sharpe | Ann. ret | Turnover | Avg gross |
|---|--:|--:|--:|--:|
| $100M | −0.10 | 2.0% | 12× | **1.81×** |
| $500M | −0.15 | 1.7% | 9× | 1.52× |
| $1B | −0.09 | 2.4% | 7× | 1.32× |
| $5B | 0.12 | 4.2% | 4× | 0.86× |
| $20B | −0.07 | 3.1% | 1× | 0.50× |
| $50B | −0.42 | 2.1% | 1× | **0.29×** |

The clean signal is the **average gross book**: it falls monotonically from 1.81× to 0.29× as capital
grows, because the participation cap increasingly prevents the strategy from filling its target — at $50B
it can only express a third of the book. Turnover collapses for the same reason. An "alpha" that runs at
$100M is a *different claim* than one that runs at $50B, and the platform now makes that ceiling visible
instead of assuming size is free.

> **Data caveat (disclosed):** the free IEX feed reports only IEX's ~4% share of consolidated volume, so
> raw ADV is understated ~25×. `run_execution.py` scales volume up by a documented factor to approximate
> true ADV; a paid consolidated feed would remove the guess. The *shape* of the curve is robust; the
> absolute dollar thresholds are approximate.

## What this demonstrates

- **Cost realism is a modeling discipline, not a constant.** Spread, impact, borrow, and partial fills
  each change the answer, and the platform prices them from real ADV/vol/spread.
- **Capacity is part of whether alpha is real.** A number that only exists at tiny size isn't a strategy;
  the capacity curve is the honest test, and it reuses the same engine — just swept over AUM.
- **Honesty about the estimator.** Corwin–Schultz is implemented *and* its liquid-name bias is disclosed;
  the default is the model that gives credible ETF spreads.

Reproduce with `python run_execution.py` (see [`REPRODUCE.md`](REPRODUCE.md)); the models are pure and
unit-tested in `tests/test_execution.py`.
