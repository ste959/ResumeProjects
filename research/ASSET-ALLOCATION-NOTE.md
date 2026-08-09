# Multi-Asset Allocation Note
### Risk-based strategic & tactical allocation across asset classes — a diversification and risk-control study

*Desk research note · liquid ETF proxies · 2020-07 – 2026-07 (~5.9y, 1,490 daily observations)*

---

## Summary

Allocating across six asset classes **by risk** rather than by naive dollar weight delivers the same
risk-adjusted return as a static 60/40 with **materially lower drawdown**, and a simple **tactical
momentum overlay** improves it further. Over 2020-07 → 2026-07, walk-forward and net of 10 bps
rebalancing cost:

| Strategy | Ann. return | Ann. vol | Sharpe | HAC t | Sharpe 95% CI | Max drawdown |
|---|--:|--:|--:|--:|:--:|--:|
| **60/40 (benchmark)** | 7.3% | 10.9% | 0.70 | 1.6 | [-0.17, 1.60] | **-21.0%** |
| Equal weight | 8.5% | 9.4% | 0.91 | 2.1 | [0.05, 1.79] | -15.9% |
| Inverse-vol | 5.7% | 8.0% | 0.73 | 1.6 | [-0.14, 1.65] | -17.8% |
| Min-variance | 0.9% | 6.8% | 0.17 | 0.4 | [-0.71, 1.08] | -18.3% |
| Max-Sharpe (MVO) | 10.9% | 14.4% | 0.79 | 1.8 | [-0.03, 1.68] | **-28.8%** |
| **Risk parity (ERC)** | 5.3% | 7.9% | 0.69 | 1.6 | [-0.17, 1.61] | -17.3% |
| **Risk parity + momentum (TAA)** | 6.6% | 9.0% | 0.76 | 1.7 | [-0.09, 1.61] | -15.9% |

The headline: **the value of risk-based allocation shows up in drawdown and stability, not a higher
return number** — the honest case for diversified, risk-managed asset allocation.

---

## Universe & method

- **Asset classes (liquid ETF proxies):** US equities (SPY), international equities (EFA), US
  Treasuries (IEF), investment-grade credit (LQD), gold (GLD), and commodities (DBC) — spanning
  equity, rates, credit, and real assets.
- **Strategic allocation (SAA):** each month, weights are fit on the trailing 1-year covariance and
  held out-of-sample. Methods:
  - **Risk parity (equal risk contribution):** each asset contributes the same share of portfolio
    variance — solved with a cyclical-coordinate algorithm that accounts for the **full covariance**,
    not just individual volatilities (the distinction inverse-vol misses).
  - **Minimum-variance** and long-only **max-Sharpe (mean-variance)**, plus inverse-vol and equal-weight.
- **Tactical overlay (TAA):** a **predictive asset-class momentum signal** (trailing 6-month return)
  tilts the risk-parity base toward asset classes with positive momentum — a lightweight "predictive
  asset-class model."
- **Honest evaluation:** all results are **walk-forward, cost-aware**, and reported with the same
  overfitting-aware statistics as the rest of the research — annualized return/vol, Sharpe, a
  **Newey–West (HAC) t-statistic**, a **block-bootstrap 95% Sharpe interval**, and max drawdown.

The allocation math is pure and unit-tested (`mds/assetalloc.py`, `tests/test_assetalloc.py` —
including a test that risk parity genuinely equalizes risk contributions and downweights redundant,
correlated assets); `run_assetalloc.py` supplies the live ETF data.

---

## What the results say

1. **Risk-based beats naive concentration on risk.** 60/40 is really a **two-asset** bet dominated by
   equity risk; broadening to six asset classes with risk parity or equal weight matches or beats its
   Sharpe while cutting the worst drawdown from **-21% to ~-16–17%**. Diversification and risk-weighting,
   not forecasting, do the work.
2. **Mean-variance optimization is fragile.** Long-only **max-Sharpe** posted the highest return but
   also the **deepest drawdown (-29%)** and the most volatility — the classic result that optimizing on
   noisy sample means concentrates the book and over-fits the past. Its wide bootstrap interval
   (lower bound below zero) says the edge is not statistically distinguishable.
3. **Min-variance is not free.** It piled into bonds and got caught in the 2022 rate shock, dragging its
   return to ~1% — low volatility is not low risk when the "safe" asset is repricing.
4. **The tactical tilt adds modest, honest value.** Momentum-tilting risk parity lifted the Sharpe
   (0.69 → 0.76) and *lowered* drawdown — a small but real improvement, not a miracle.

**Caveats (stated plainly):** ~5.9 years is a single, unusual regime (a bond bear market inside the
sample), so none of these Sharpes clears a strict multiple-testing bar — the HAC t-stats sit near 1.5–2
and most bootstrap intervals touch zero. This is a **framework and risk-control demonstration**, not a
claim of a statistically bullet-proof allocation edge. The ETF proxies also carry their own fees and
tracking error, abstracted away here.
