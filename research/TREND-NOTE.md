# Trend-Following Note
### Enhanced multi-asset time-series momentum — what the enhancements actually add, by ablation

*Desk research note · 13 liquid ETF proxies · 2020-07 – 2026-07 (~5.9y) · excess of a BIL T-bill risk-free rate*

---

## Summary

A diversified time-series-momentum (trend) book, built up one enhancement at a time and judged by the
same overfitting-aware gauntlet as the rest of the research. The honest findings:

1. **One layer does the work, and it's a *risk-management* layer, not a signal.** Adding a
   correlation-aware **portfolio vol-target** lifts excess Sharpe from **0.24 (vanilla) to 0.60** — the
   single biggest jump in the ablation. This matches the literature (Harvey et al. 2018): most of trend's
   risk-adjusted quality comes from *sizing*, not from a cleverer trend signal.
2. **More signal knobs did *not* mean more alpha.** Blending in **carry** and **crash-protection** on top
   of the vol-targeted book did **not** improve this sample (carry actually lowered Sharpe 0.60 → 0.24; a
   cross-sectional overlay recovered part of it to 0.38). That is the honest "researcher-degrees-of-freedom"
   result — added complexity that doesn't earn its keep is reported as such, not quietly dropped.
3. **Nothing clears the significance bar — but the *regime* story is the real point.** No ablation variant
   clears the multiple-testing t-bar, and the sample is underpowered (min-detectable Sharpe ≈ 1.27). Yet
   the full system earned **excess Sharpe 1.77 in 2022** — the rate-shock year where *every* allocation
   strategy in [`ASSET-ALLOCATION-NOTE.md`](ASSET-ALLOCATION-NOTE.md) lost together. Trend's contribution
   isn't a big headline Sharpe; it's **crisis convexity** — a diversifying premium that pays precisely when
   diversification-by-correlation fails.

## The ablation (walk-forward, net of 10 bps, 10% vol target, excess of cash)

Each row adds one enhancement to the row above it, so the change in each column *is* that enhancement's
marginal contribution.

| Ablation stage | Ann. ret | Ann. vol | **Excess Sharpe** | HAC t | Max DD | Sortino | Skew |
|---|--:|--:|--:|--:|--:|--:|--:|
| vanilla (1-lookback sign) | 5.1% | 7.1% | 0.24 | 0.5 | -12.1% | 0.31 | -0.61 |
| + vol-targeting | 4.2% | 5.3% | 0.14 | 0.3 | -10.0% | 0.18 | -0.63 |
| + multi-timescale | 3.6% | 5.9% | 0.03 | 0.1 | -13.8% | 0.04 | -0.62 |
| **+ portfolio vol-target** | 10.1% | 11.2% | **0.60** | 1.4 | -17.4% | **0.85** | **-0.15** |
| + carry blend | 5.9% | 12.0% | 0.24 | 0.5 | -18.9% | 0.35 | -0.11 |
| + crash-protection | 5.7% | 11.0% | 0.24 | 0.5 | -16.8% | 0.35 | -0.09 |
| + cross-sectional | 7.3% | 10.7% | 0.38 | 0.9 | -13.1% | 0.54 | -0.30 |

Read honestly: the per-asset vol-targeting and multi-timescale steps barely moved (or slightly hurt) the
Sharpe on their own; the **portfolio-level constant-vol overlay** is what mattered, because it sizes the
whole book against the covariance and pushes real risk into the trends worth taking. The signal blends
after it are, on this universe and window, complexity that didn't pay.

## Selection-aware gauntlet (7 ablation variants, ~1,219 days)

The seven ablation builds are themselves a strategy *set* tried on one path — so the same multiple-testing
correction applies here as everywhere in the repo.

| Check | Value | Bar | Verdict |
|---|--:|:--|:--|
| Best excess Sharpe | 0.60 (`+ portfolio vol-target`) | — | — |
| Best HAC t-stat | 1.38 | \|t\| > 2.69 (Bonferroni) | **fails** |
| Deflated Sharpe | 0.78 | > 0.95 | fails |
| PBO (overfit prob.) | 0.39 | < 0.5 | passes |
| Min-detectable Sharpe | 1.27 | ≤ best | **underpowered** |

The point estimate is positive and economically sensible, but it is **not** a statistically established
edge on this sample — and the note says so.

## Regime robustness (full system, excess Sharpe / max drawdown)

| Sub-period | Excess Sharpe | Max DD |
|---|--:|--:|
| 2020-21  zero-rate / recovery | 0.71 | -6.6% |
| **2022  rate shock (stocks + bonds)** | **1.77** | -8.7% |
| 2023-26  higher-for-longer | -0.18 | -9.0% |

This is the table that carries the thesis. Trend's best year is 2022 — the one regime where the
allocation study's every method lost, because the stock/bond correlation flipped positive and static
diversification stopped diversifying. Trend went short duration and long the dollar/commodities into the
move. Its weakness is equally visible: **2023-26 is negative** — the choppy, mean-reverting, "higher-for-
longer" chop that whipsaws trend. Both are the *expected* behavior from
[`SIGNAL-RATIONALE.md`](SIGNAL-RATIONALE.md), shown rather than hidden.

## Sensitivity (18 configs of rebalance × cost × vol-target)

Full-system excess Sharpe ranges **[0.15, 0.76]**, median **0.51**; **18/18** configurations are positive
but **0/18** reach \|HAC t\| ≥ 1.96. The *sign* of the effect is robust to the arbitrary choices; its
*significance* is not — consistent with a real-but-modest premium the sample is too short to prove.

## What this demonstrates

- **The right lever.** The biggest risk-adjusted gain came from portfolio-level vol-targeting, not signal
  tinkering — the senior-desk answer, and the one the ablation makes *visible*.
- **Honesty about complexity.** Carry and crash-protection were added for stated economic reasons, tested,
  and reported as *not* helping on this sample. The apparatus exists to catch exactly that.
- **The value is convexity, not a Sharpe.** Trend earns its place in a book by paying in the regime where
  everything else fails together (2022) — a diversification benefit a single full-sample Sharpe erases.

Reuses the shared [`mds/evaluation.py`](mds/evaluation.py) harness (the same excess-of-cash Sharpe, HAC
t-stat, bootstrap CI, tail metrics, and PBO/Deflated-Sharpe gauntlet as the allocation study), so this
book is measured on an identical stick. Reproduce with `python run_trend.py` (see
[`REPRODUCE.md`](REPRODUCE.md)); the trend math is pure and unit-tested in `tests/test_trend.py`.
