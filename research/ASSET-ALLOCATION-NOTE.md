# Multi-Asset Allocation Note
### Risk-based strategic & tactical allocation across asset classes — a diversification and risk-control study

*Desk research note · liquid ETF proxies · 2020-07 – 2026-07 (~5.9y, 1,490 daily observations)*

---

## Summary

Across six asset classes, walk-forward and net of cost, the honest finding is that **simple
diversification (equal weight) posted the best risk-adjusted return on this sample — and that *no*
allocation method clears a selection-aware significance bar.** The sophisticated allocators (risk
parity, min-variance, mean-variance) did **not** beat 1/N here, echoing the well-known DeMiguel–Garlappi–Uppal
(2009) result. This is a **framework and risk-control demonstration, not a statistically established
allocation edge** — a conclusion the pipeline reaches on its own, not a hand-picked verdict.

| Strategy | Ann. return | Ann. vol | Sharpe | HAC t | Sharpe 95% CI | Max drawdown |
|---|--:|--:|--:|--:|:--:|--:|
| 60/40 (benchmark) | 7.3% | 10.9% | 0.70 | 1.6 | [-0.17, 1.60] | -21.0% |
| **Equal weight (1/N)** | 8.4% | 9.4% | **0.91** | 2.1 | [0.04, 1.79] | -15.9% |
| Inverse-vol | 5.7% | 8.0% | 0.73 | 1.6 | [-0.14, 1.65] | -17.8% |
| Min-variance | 1.7% | 6.9% | 0.28 | 0.6 | [-0.58, 1.19] | -18.9% |
| Max-Sharpe (MVO) | 11.9% | 14.8% | 0.83 | 1.9 | [0.02, 1.72] | **-28.7%** |
| Risk parity (ERC) | 5.3% | 7.9% | 0.69 | 1.6 | [-0.17, 1.61] | -17.3% |
| Risk parity + momentum (TAA) | 6.6% | 9.0% | 0.76 | 1.7 | [-0.09, 1.61] | -15.9% |

**Selection-aware gauntlet** (the same one the equity study runs — because backtesting 7 strategies on
one path *is* multiple testing):

| Test | Value | Bar | Verdict |
|---|--:|:--|:--|
| Best strategy | equal weight | — | Sharpe 0.91, HAC t 2.09 |
| Multiple-testing bar | \|t\| 2.09 | > 2.69 (Bonferroni, 7 trials) | **FAILS** |
| Deflated Sharpe | 0.92 | > 0.95 | **not a genuine edge** |
| PBO (CSCV) | 0.65 | < 0.5 | **probably overfit** |
| Min-detectable Sharpe | 0.91 vs 1.26 | — | **underpowered** |

---

## Universe & method

- **Asset classes (liquid ETF proxies):** US equities (SPY), international equities (EFA), US
  Treasuries (IEF), investment-grade credit (LQD), gold (GLD), commodities (DBC) — spanning equity,
  rates, credit, and real assets.
- **Strategic allocation (SAA):** each month, weights are fit on the trailing 1-year covariance and held
  out-of-sample. Methods: **risk parity (equal risk contribution)** — solved with a cyclical-coordinate
  algorithm that uses the **full covariance** (the correlation-awareness inverse-vol lacks); **minimum-variance**
  and long-only **max-Sharpe**, both on a **Ledoit-Wolf-shrunk covariance** with an optimizer-failure fallback
  (naive mean-variance error-maximizes on a raw, ill-conditioned sample cov); plus inverse-vol and equal-weight.
- **Tactical overlay (TAA):** a time-series-momentum asset-class signal (trailing 6-month return) tilts the
  risk-parity base toward positive-momentum assets — a lightweight predictive asset-class model.
- **Honest evaluation:** all results are **walk-forward and cost-aware** — turnover is charged against the
  *drifted* holdings each rebalance (so even a static 60/40 pays realistic rebalancing cost) — and scored with
  the full gauntlet above: Newey–West (HAC) t, block-bootstrap Sharpe CI, **Deflated Sharpe, PBO, and a
  min-detectable-Sharpe power check**.

Pure and unit-tested (`mds/assetalloc.py`, `tests/test_assetalloc.py` — including a test that risk parity
equalizes risk contributions and downweights redundant, correlated assets); `run_assetalloc.py` supplies the
live ETF data.

---

## What the results say

1. **1/N is a hard benchmark to beat.** Equal weight matched or beat every optimized method on Sharpe and
   drawdown. Estimation error in the optimizers' inputs — covariances and especially means — outweighs the
   benefit of "optimizing" on a single ~6-year path. This is the DeMiguel result reproduced honestly, and it's
   the finding a naive "risk parity wins" writeup would have buried.
2. **Mean-variance optimization is fragile even with shrinkage.** Long-only **max-Sharpe** posted the highest
   return but the **deepest drawdown (-29%)** and the most volatility — it concentrates into whatever looked
   best in-sample. Ledoit-Wolf shrinkage tames it somewhat but does not fix the mean-estimation problem.
3. **Min-variance is not low risk.** It over-weighted bonds into the 2022 rate shock and returned ~2% — low
   *volatility* is not low *risk* when the "safe" asset is repricing.
4. **Nothing clears the bar.** The best strategy fails the Bonferroni-corrected t-bar, has a Deflated Sharpe
   below 0.95 and a PBO of 0.65, and the sample can't reliably detect a Sharpe below ~1.26. **Correctly, the
   study claims no edge.**

**Where risk parity's case actually lives:** not in this sample's Sharpe, but in **stability and drawdown
control across regimes** — a property one favorable ~6-year path (with a single embedded bond bear market)
cannot establish. Proving it needs multiple regimes and a longer, survivorship-free history. The ETF proxies
also carry their own fees and tracking error, abstracted away here.
