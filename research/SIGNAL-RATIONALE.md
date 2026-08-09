# Signal rationale, failure modes & alpha decay

A signal with an economic story is evidence; a signal that only exists in a backtest is a coincidence
until proven otherwise. This document states, for each signal in the research, **why it should work**,
**when it should fail**, and how **crowding and decay** are expected to erode it — the market-understanding
that separates a researcher from a backtest tourist.

## Cross-sectional equity signals

| Signal | Why it should work (economic story) | When it fails | Crowding / decay |
|---|---|---|---|
| **Momentum (12–1)** | Under-reaction to news + a risk premium for holding trending losers-vs-winners | **Momentum crashes** at sharp reversals (2009) — short leg rallies violently | Heavily published/traded → premium compressed; needs risk management, not just the raw signal |
| **Value** | Risk premium for distressed/cheap firms + mispricing from over-extrapolation | Value traps; the 2010s "lost decade" as growth dominated | Well-known; works best where data is worst (small, illiquid) — the opposite of this mega-cap universe |
| **Quality** | Profitable, low-accrual, low-leverage firms are under-priced for their stability | Quality gets expensive; underperforms in junk rallies | Robust but modest; blends well, not a standalone edge |
| **Low-volatility / BAB** | Leverage-constrained investors overpay for high-β "lottery" names, leaving low-β under-priced | Rate-sensitive (a bond proxy); crushed when rates spike (2022) | Crowded post-2010; much of the premium arbitraged |
| **Short-term reversal** | Compensation for providing liquidity to forced sellers; overreaction correction | The gross edge is real but **smaller than the spread** — dies to transaction cost | Only survives with cheap execution; a market-making, not a taker, strategy |

**Why the honest null on this universe is *expected*:** these signals are strongest on small, illiquid,
poorly-covered names. Run on today's US mega-caps — the most-traded, most-arbitraged, best-covered stocks,
with only free daily price/volume data — the efficient-market prior should dominate, and it does. The null
is the economically-correct answer, not a failure of technique.

## Microstructure

- **Order-flow imbalance (OFI):** signed order flow moves the next price because it carries information
  (Cont–Kukanov–Stoikov). Genuinely predictive at very short horizons — but the IC **decays like ~IC/√h**
  as the informative move is diluted by later noise, and at tick frequency the predicted move is often
  **smaller than the spread**, so a predictive signal is not a tradable one. The event-driven study
  measures exactly that gap (on a synthetic, known-IC tape — a plumbing check, not a measured edge).

## Multi-asset (allocation)

- **Time-series (trend) momentum** on asset classes: trend-following captures under-reaction to
  macro shifts and provides convexity in sustained moves. **Fails in choppy, mean-reverting markets**
  (whipsaw) and at trend turns. In this study it added modest value but nothing significant.
- **Risk parity / diversification** is a bet on **stable correlations**. Its failure mode is exactly
  2022: when the stock/bond correlation flips positive, "diversified" books fall together — the one row
  in the allocation note where every method lost.

## Alpha decay & crowding

Published anomalies decay. McLean & Pontiff (2016) document that factor returns fall ~30–60% after
publication as capital arbitrages them; the most-cited signals decay most. This project's results are
consistent with that world:

- The **honest null on mega-caps** is what a decayed, crowded, efficiently-priced cross-section looks
  like — the signal that may still exist in obscure corners is gone from the names everyone trades.
- The **microstructure IC decay curve** (IC by horizon) is the *within-signal* version of the same
  story: informational edge is largest at the shortest horizon and fades fast.
- The honest posture that follows: assume any apparent edge is **already decaying or already arbitraged**
  until it survives out-of-sample, across regimes, and net of realistic cost. The value the research
  actually demonstrates is not signal discovery but **construction, risk control, and knowing the
  difference between a predictive signal and a tradable one.**
