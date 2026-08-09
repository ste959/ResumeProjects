# Multi-Asset Allocation Note
### Risk-based strategic & tactical allocation across asset classes — diversification, tail risk, and regime robustness

*Desk research note · liquid ETF proxies · 2020-07 – 2026-07 (~5.9y) · excess of a BIL T-bill risk-free rate*

---

## Summary

Across six asset classes, walk-forward and net of cost, **no allocation method establishes a
statistically significant edge** — not in aggregate, not in any sub-period, and not under any of 18
parameter configurations. The interesting, honest findings are methodological and market-structural:

1. **Excess of cash matters enormously here.** Over 2020–26 the T-bill went from ~0% to ~5%; measuring
   Sharpe on *raw* returns overstated everything. On the correct excess-of-cash basis, headline Sharpes
   roughly halve (equal-weight 0.91 → **0.55**, 60/40 0.70 → **0.37**).
2. **The highest Sharpe carries the worst tail.** Max-Sharpe (mean-variance) posts the top excess Sharpe
   (0.63) but the deepest drawdown (−29%), the worst expected shortfall (−2.3%/day), and **negative skew** —
   while equal-weight wins on the *downside*-adjusted measures (Sortino 0.80, Calmar 0.54, positive skew).
   Sharpe alone is a misleading ranking.
3. **Diversification failed exactly when it was needed.** In 2022 *every* strategy had a negative Sharpe —
   the stock/bond correlation flipped positive, so "diversified" books fell together.

| Strategy | Ann. ret | Ann. vol | **Excess Sharpe** | HAC t | Sharpe 95% CI | Max DD | Sortino | Calmar | CVaR-5% | Skew |
|---|--:|--:|--:|--:|:--:|--:|--:|--:|--:|--:|
| 60/40 | 7.2% | 10.9% | 0.37 | 0.8 | [-0.48, 1.21] | -21.0% | 0.53 | 0.34 | -1.55% | 0.18 |
| **Equal weight (1/N)** | 8.6% | 9.4% | 0.55 | 1.3 | [-0.27, 1.39] | -15.9% | **0.80** | **0.54** | -1.31% | 0.11 |
| Inverse-vol | 5.8% | 8.0% | 0.30 | 0.7 | [-0.56, 1.15] | -17.9% | 0.45 | 0.32 | -1.10% | 0.23 |
| Min-variance | 1.8% | 7.0% | -0.21 | -0.5 | [-1.07, 0.60] | -18.7% | -0.31 | 0.10 | -0.95% | 0.18 |
| Max-Sharpe (MVO) | 12.6% | 15.0% | **0.63** | 1.4 | [-0.14, 1.50] | **-29.0%** | 0.79 | 0.43 | **-2.29%** | **-0.73** |
| Risk parity (ERC) | 5.5% | 8.0% | 0.27 | 0.6 | [-0.59, 1.11] | -17.4% | 0.40 | 0.31 | -1.10% | 0.21 |
| Risk parity + momentum (TAA) | 7.0% | 9.1% | 0.40 | 0.9 | [-0.42, 1.26] | -15.9% | 0.57 | 0.44 | -1.29% | -0.09 |

**Selection-aware gauntlet** (across 7 strategies, 1,223 days): best is max-Sharpe (excess 0.63, HAC t 1.44),
which **FAILS** the Bonferroni bar (\|t\| > 2.69); **Deflated Sharpe 0.71** (< 0.95), **PBO 0.48**,
**min-detectable Sharpe 1.27 → underpowered**. The study claims no edge — correctly.

**Regime robustness** (excess Sharpe by sub-period — the ranking is *not* stable):

| Regime | 60/40 | Equal | Inv-vol | Min-var | Max-Sh | Risk-par | RP+TAA |
|---|--:|--:|--:|--:|--:|--:|--:|
| 2020–21 zero-rate / recovery | 1.41 | 1.12 | 0.75 | -0.15 | 1.19 | 0.70 | 0.64 |
| **2022 rate shock** | **-1.15** | **-0.69** | **-1.17** | **-1.57** | **-0.10** | **-1.13** | **-0.86** |
| 2023–26 higher-for-longer | 1.03 | 1.04 | 0.92 | 0.40 | 0.98 | 0.86 | 0.86 |

**Sensitivity sweep** (18 configs of lookback × rebalance frequency × cost): the winner is unstable
(max-Sharpe in 11, equal-weight in 7), and **0 of 18 configurations clear the multiple-testing bar** — the
null is robust to every arbitrary choice.

---

## Universe & method

- **Asset classes (liquid ETF proxies):** US equities (SPY), international equities (EFA), US Treasuries
  (IEF), IG credit (LQD), gold (GLD), commodities (DBC). **Risk-free rate:** BIL (1–3m T-bill ETF).
- **Strategic allocation (SAA):** monthly, weights fit on the trailing 1-year covariance and held
  out-of-sample — **risk parity (equal risk contribution)** on the full covariance (correlation-aware,
  unlike inverse-vol), **minimum-variance** and long-only **max-Sharpe** on a **Ledoit-Wolf-shrunk**
  covariance with an optimizer-failure fallback, plus inverse-vol and equal-weight.
- **Tactical overlay (TAA):** a time-series-momentum asset-class signal tilts the risk-parity base.
- **Evaluation:** walk-forward; turnover charged against *drifted* holdings each rebalance; all
  performance **in excess of the risk-free rate**; scored with HAC t, block-bootstrap CI, **Deflated
  Sharpe, PBO, power**, plus **downside/tail metrics** (Sortino, Calmar, CVaR, skew); and re-run across
  **regimes** and a **parameter sweep**.

Pure and unit-tested (`mds/assetalloc.py`, `tests/test_assetalloc.py`); reproducible from cached data with
fixed seeds (`run_assetalloc.py`, see [`REPRODUCE.md`](REPRODUCE.md)).

---

## What the results say

- **1/N is hard to beat, and it wins where it matters.** Equal weight leads every optimized method on
  downside-adjusted return (Sortino, Calmar) with positive skew — the DeMiguel–Garlappi–Uppal (2009)
  result. Estimation error in the optimizers' inputs outweighs the benefit of optimizing on one path.
- **Optimization buys Sharpe with tail risk.** Max-Sharpe's higher Sharpe comes bundled with the worst
  drawdown and a fat left tail (skew −0.73). A manager who ranked on Sharpe alone would have bought the
  most fragile book.
- **Correlations are not constant.** The 2022 row is the whole point: diversification is a correlation
  bet, and when stock/bond correlation flipped positive, every allocation lost together. Static
  risk models estimated on trailing data are blind to this until it happens.
- **Nothing is significant, robustly.** Best HAC t 1.44 < the 2.69 bar; DSR 0.71; PBO 0.48; underpowered;
  and 0/18 parameterizations clear the bar. This is an honest null, not a tuning failure.

**Where risk parity's case actually lives:** not this sample's Sharpe, but stability and drawdown control
*across* regimes — which one ~6-year path (with a single embedded rate shock) cannot establish. Proving it
needs multiple regimes and a longer, survivorship-free history. The ETF proxies also carry their own fees
and tracking error, abstracted away here.
