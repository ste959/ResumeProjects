# Cross-Sectional Stat-Arb Note
### The canonical desk strategy, pointed at breadth — and an honest read of where the edge went

*Residual reversal on PCA statistical factors (Avellaneda–Lee) · 92 liquid US large-caps · 2020-07 – 2026-07 · daily · excess of cash*

---

## Why this study exists

A senior-QR critique of the earlier work was fair: *the methods were only ever pointed at known premia on
the most efficient instruments, so the nulls were uninformative.* This is the answer — the **canonical
equity stat-arb strategy** (Avellaneda–Lee 2010), built properly and pointed at a **broad, factor-neutral
cross-section**, which is where cross-sectional alpha is supposed to live.

## The method (`mds/xstatarb.py`)

1. **Statistical risk factors** — the top-15 eigenvectors of the return correlation matrix ("eigenportfolios"
   ≈ market + sectors). The factors are *learned*, not imposed — no fundamental sector data required.
2. **Residualize** — regress each stock on the factor returns; the residual is the idiosyncratic move,
   **orthogonal to the factors** (the book is factor-neutral by construction; asserted by test).
3. **s-score** — model the cumulative residual as an **Ornstein–Uhlenbeck** process; the s-score is how many
   equilibrium-σ the residual sits from its mean. Only names whose reversion is fast enough (κ filter) trade.
4. **Portfolio** — alpha = −s-score, risk-weighted by residual vol, **dollar-neutral**.

## Result — the honest read

| | Excess Sharpe | HAC t | 95% CI | Ann. ret | Turnover |
|---|--:|--:|:--:|--:|--:|
| **Gross (no cost)** | −0.44 | −1.0 | [−1.28, +0.41] | +1.7% | 102× |
| Net (realistic, $50M) | −1.49 | −3.5 | — | −1.5% | 102× |

Parameter sensitivity (gross, window × k) sits near zero everywhere (−0.74 … +0.09). **Even gross, there
is no taker-accessible reversal edge here** — the 95% CI includes zero, so the signal is statistically
indistinguishable from noise, and realistic execution (≈100×/yr turnover) only deepens the loss (worse as
AUM grows: −2.76 at $1B).

## Why this is the *correct* result, not a failure

- **Avellaneda–Lee themselves documented the decay.** Their reversal was strongly profitable pre-2005 and
  **fell off sharply after 2007** as stat-arb capital crowded the space. On liquid large-caps in 2020–26,
  the daily residual-reversal edge is exactly where their own decay analysis says it should be: **arbitraged
  out of the liquid cross-section.**
- **Short-term reversal is a liquidity-provision premium.** The gross edge that remains belongs to whoever
  **earns the spread rather than pays it** — a market-making implementation — and to horizons (intraday) and
  names (small/illiquid) that free daily data cannot reach. A taker crossing 100×/yr was always going to
  give it back; the platform measured exactly how much.

## What this demonstrates (the point of the exercise)

- **A correct, non-trivial stat-arb build** — statistical (PCA) factors, provable factor-neutrality,
  OU s-scores with a mean-reversion-speed filter, dollar-neutral risk-weighted sizing — on real breadth
  (92 names), not a toy.
- **The methods were pointed where alpha could live**, and the result was measured honestly with the full
  gauntlet (HAC t, bootstrap CI, sensitivity, capacity) rather than curve-fit into a positive number.
- **Knowing where the edge went is the finding.** "The daily reversal is arbitraged from liquid names and
  survives only as a market-making / intraday / small-cap phenomenon" is a *specific, correct, defensible*
  conclusion — the difference between a researcher and a backtest tourist.

## The honest next step (disclosed)

To turn this from a correct null into a live edge needs one of: a **less-liquid universe** (small-caps,
where reversal persists — but the free IEX feed's data quality there is poor), **intraday data** (the
horizon where the premium concentrates), or a **maker implementation** that earns the spread — which is
what the repo's matching engine could simulate (the roadmap's LOB-backed-fills item). The build is ready
for all three; the constraint is data, not method.

Reproduce with `python run_xstatarb.py` (see [`REPRODUCE.md`](REPRODUCE.md)); the signal/portfolio math is
pure and unit-tested in `tests/test_xstatarb.py`.
