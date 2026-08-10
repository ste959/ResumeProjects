# Trend-Following Note
### Enhanced multi-asset time-series momentum — what the enhancements actually add, by ablation

*Desk research note · 13 liquid ETF proxies · 2020-07 – 2026-07 (~5.9y) · excess of a BIL T-bill risk-free rate*

---

## Summary

A diversified time-series-momentum (trend) book, built up one enhancement at a time, then **taken apart
by a diagnostics pass** to attribute every number to a mechanism. The ablation looked like a tidy story;
the diagnostics revised it into a more honest — and more interesting — one:

1. **It isn't the trend signal.** With constant gross exposure, the signal *alone* Sharpes **0.03**. Nearly
   all of the headline **0.60** comes from **volatility-timing** (scaling exposure by inverse vol over time —
   a Moreira–Muir effect); correlation-aware sizing adds a little on top. Trend direction is close to free
   here; the risk-*sizing* is doing the work (consistent with Harvey et al. 2018, taken to its logical end).
2. **Carry is a genuine detractor, confirmed order-independently.** Leave-one-out (remove one enhancement
   from the full system) shows removing **carry lifts** the full system 0.38 → **0.54** — so the "full"
   build isn't even the best, and carry's damage wasn't just an artifact of where it sat in the cumulative
   chain. Added complexity that doesn't earn its keep is reported, not quietly dropped.
3. **None of the "improvements" are statistically established.** A paired block-bootstrap of the Sharpe
   *difference* puts peak-vs-vanilla at ΔSharpe **+0.36, 95% CI [−0.28, +1.01]** — indistinguishable from
   noise. Nothing clears the multiple-testing bar; the sample is underpowered (min-detectable Sharpe ≈ 1.27).
4. **The "2022 crisis convexity" is largely a factor bet.** Regressed on equity and duration, the book is
   **equity-neutral (β_eq ≈ 0)** but carries a large, *highly* significant **short-duration beta −0.29
   (t −16.7)**. Sleeve attribution confirms 2022 was **short credit/rates + long commodities/dollar** — a
   *static* short-bond tilt cashing in during a bond bear market, more than pure convexity.

**Honest bottom line:** what looks like "enhanced trend alpha" is mostly **vol-timing plus a short-duration
factor tilt** — a useful, equity-neutral, diversifying return stream, but not signal-driven alpha, and not
statistically proven on ~6 years. The value of this note is the *method*: it turns a murky Sharpe into a
mechanism you can name, argue with, and size honestly.

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

## Diagnostics — attributing the numbers instead of reporting them

The point estimates above are murky (why did that one step jump? is it real? what is the book doing?).
Five diagnostics resolve each ambiguity. This is where the actual understanding is.

**[1] Vol-target decomposition** (signal fixed; split the vol overlay into its mechanisms):

| Variant | Excess Sharpe | Ann. vol | Avg gross |
|---|--:|--:|--:|
| constant gross (signal only) | **0.03** | 5.9% | 1.00× |
| + scalar vol-target (timing, no correlation) | 0.52 | 16.7% | 2.83× |
| + covariance vol-target (adds correlation) | 0.60 | 11.2% | 2.07× |

The signal alone is worth ~nothing; the 0.03 → 0.52 jump is **vol-timing**, and 0.52 → 0.60 is
correlation-awareness. This is the single most important row in the study.

**[2] Leave-one-out** (remove one enhancement from the full system; Δ vs. full 0.38):

| Removed | Excess Sharpe | Δ | Reading |
|---|--:|--:|:--|
| portvol | −0.03 | −0.41 | essential |
| voltarget | 0.19 | −0.19 | helps |
| xs (cross-sectional) | 0.24 | −0.14 | helps |
| multiscale | 0.34 | −0.04 | ~neutral |
| crash-protection | 0.41 | +0.03 | mildly hurts |
| **carry** | **0.54** | **+0.16** | **hurts — drop it** |

Order-independent, so it corrects the cumulative ablation: carry is a real detractor, and the "full"
system is *not* the best build.

**[3] Sleeve attribution** (full system; avg gross 2.1×, annual turnover ~11×):

- **Net exposure:** short Rates (−0.38) & Credit (−0.33), long Equity (+0.23) & Commodity (+0.18), flat USD.
- **Total P&L:** Commodity **+30.5%**, Equity **+18.5%** drove it; USD **−6.0%** detracted.
- **2022 P&L:** Credit +9.0%, Commodity +7.0%, Rates +6.0%, USD +3.9%, Equity −1.1% — short credit/duration
  and long real-assets/dollar were the crisis winners.

**[4] Are the gains real?** Paired block-bootstrap of the Sharpe *difference* (same dates, so market moves
cancel): peak-vs-vanilla ΔSharpe **+0.36, 95% CI [−0.28, +1.01]**; full-vs-peak **−0.22, [−0.91, +0.45]**.
Both CIs span zero — **not distinguishable from noise**.

**[5] Factor exposure** (regress excess book return on SPY & TLT):

| | α (ann.) | α t | β equity | β duration | R² |
|---|--:|--:|--:|--:|--:|
| Full sample | +2.1% | 0.5 | +0.00 (t 0.2) | **−0.29 (t −16.7)** | 0.19 |
| 2022 only | — | — | −0.28 | −0.27 | — |

Equity-neutral, but a large and *persistent* short-duration beta — and 2022's duration beta (−0.27) is no
larger than the full-sample tilt (−0.29). So the "crisis convexity" is substantially a **static short-bond
factor bet** that paid off in a bond bear market, not a dynamic response the signal generated.

## What this demonstrates

- **The right question is "what mechanism," not "what Sharpe."** The diagnostics reattributed the whole
  result: from "enhanced trend alpha" to "vol-timing + a short-duration factor tilt, equity-neutral, not
  statistically proven." That reattribution *is* the skill.
- **Honesty about complexity and significance.** Carry was added for a stated economic reason, tested, and
  shown (order-independently) to *hurt*. And a paired bootstrap says none of the ablation gains are
  distinguishable from noise — reported plainly rather than sold as an edge.
- **Know your betas.** The single most useful check was the factor regression: it caught that the headline
  story ("crisis convexity") was mostly a persistent short-duration exposure. A book you can't decompose
  into its factor bets is a book you don't understand.

Reuses the shared [`mds/evaluation.py`](mds/evaluation.py) harness (the same excess-of-cash Sharpe, HAC
t-stat, bootstrap CI, tail metrics, and PBO/Deflated-Sharpe gauntlet as the allocation study), so this
book is measured on an identical stick. Reproduce with `python run_trend.py` (see
[`REPRODUCE.md`](REPRODUCE.md)); the trend math is pure and unit-tested in `tests/test_trend.py`.
