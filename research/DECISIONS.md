# Research log & researcher degrees of freedom

An honest account of what was tried, what didn't work, and why the significance statistics should be
read *more* conservatively than the reported trial counts suggest. The point of this document is the
thing most backtests hide: **the search was wider than the final table shows.**

## Why this matters

The overfitting corrections in this repo (Deflated Sharpe, Bonferroni, PBO) deflate for the number of
*final* candidates — 11 equity factors, 7 allocation methods. But the real search space also includes
every design choice that was fixed by hand and not swept: lookback windows, neutralization schemes,
winsorization levels, universe, rebalance frequency, cost assumptions. Each is an implicit test.
**The reported corrected bars are therefore optimistic**, and the honest reading is: treat any result
that *barely* clears a bar as not clearing it.

This cuts one way here, which is why the project can state it plainly: **the headline conclusions are
nulls.** A null that survives a wide search is *strengthened* by the extra degrees of freedom, not
weakened. The discipline matters most for the day a result *does* look significant — the whole apparatus
exists to keep that day honest.

## What was tried (the search, not just the winners)

**Cross-sectional equity factors (`run_crosssec.py`)**
- ~18 factors across value / quality / momentum / low-risk / reversal / flow families.
- Lookbacks tried per family (12–1 vs 6–1 momentum; 1-week vs 1-month reversal; various vol windows).
- Neutralization: raw vs β-neutral vs β+sector-neutral. Winsorization on/off.
- Universe: today's US mega-caps (a *known* survivorship limitation, disclosed).
- **Result: honest null.** No factor clears a Bonferroni-corrected \|t\|; best Deflated Sharpe ≈ 0.08.

**Portfolio construction (`run_construction.py`, `run_portfolio.py`)**
- Multi-factor composite; factor risk-model MVO (Σ=BFBᵀ+D); regime timing (credit/VIX); options
  structuring; tax-aware rebalancing.
- **Result:** construction/risk-control adds real value (⅓ the drawdown) *without* a significant
  standalone signal — reported as such, not dressed up as alpha.

**Microstructure (`run_microstructure.py`)**
- Order-flow-imbalance event-driven study on a *synthetic, known-IC* tape (a plumbing/validation check,
  labeled as such — the IC is assumed, not measured); maker-execution / adverse-selection study.

**Multi-asset allocation (`run_assetalloc.py`)**
- 7 allocators; a 18-config lookback × rebalance × cost sweep; 3 calendar-regime splits.
- **Result:** nothing clears the bar in *any* configuration; equal-weight wins on downside measures.

**Enhanced trend-following (`run_trend.py`)**
- A 7-stage ablation (vol-targeting, multi-timescale signal, portfolio vol overlay, carry, crash-
  protection, cross-sectional overlay) over a 13-market universe; 18-config sweep; 3 regimes; then a
  **diagnostics pass** (vol-target decomposition, leave-one-out, sleeve attribution, paired Sharpe-diff
  bootstrap, factor-beta regression) to attribute every number.
- **Result (as revised BY the diagnostics — the important part):** the trend *signal* is worth ~nothing
  (constant-gross Sharpe 0.03); nearly all of the 0.60 is **vol-timing** (Moreira–Muir), not direction.
  Leave-one-out confirms **carry hurts** (removing it lifts the full system 0.38 → 0.54) order-
  independently. A paired bootstrap says the ablation gains are **not distinguishable from noise**
  (peak-vs-vanilla ΔSharpe +0.36, CI [−0.28, +1.01]). And the factor regression caught that the headline
  "2022 crisis convexity" is largely a **static short-duration beta (−0.29, t −16.7)** cashing in during a
  bond bear market — the book is equity-neutral but is really vol-timing + a duration tilt, not signal alpha.
- **The lesson this logs:** the first-pass narrative ("risk-management lever + crisis convexity") was
  half-right and half-artifact; only the diagnostics separated the mechanism from the story. Decompose the
  book into its factor bets before believing your own summary.

**Cross-sectional statistical arbitrage (`run_xstatarb.py`)**
- The canonical desk build — Avellaneda–Lee residual reversal: top-15 PCA eigenportfolio factors →
  residualize (factor-neutral) → OU s-scores → dollar-neutral, on 92 liquid large-caps, daily.
- **Result: an *informative* null.** Even gross, excess Sharpe ≈ −0.44 with a 95% CI of [−1.28, +0.41]
  (includes zero) and near-zero across every window×k — the daily reversal is **arbitraged out of the
  liquid cross-section**, exactly as Avellaneda–Lee's own post-2007 decay documents. This is a *different*
  and stronger null than the mega-cap factor one: the methods were pointed where alpha can live (breadth,
  factor-neutral residuals), built correctly, and the honest measurement shows the taker edge is gone;
  what remains is a market-making / intraday / small-cap phenomenon free daily data can't reach.

**OPEX structural effect + alpha-decay monitor (`run_opex.py`)**
- Hypothesis: the dealer-gamma cycle leaves the week after monthly expiry weak (a *structural*, mechanical
  effect). Tested on SPY/QQQ/IWM; built the alpha-decay/crowding monitor to judge the lifecycle.
- **Result: the textbook sign REVERSED** — post-OPEX was the *strongest* phase this sample (t≈+2.8), not
  the weakest, so the published trade (flat post-OPEX) *underperforms* buy-and-hold. And the crowding
  detector made the decisive catch: the timing overlay is +0.90 correlated to SPY and rising — **beta
  wearing an alpha costume, not an independent edge.** The deliverable is the monitor (catch a false
  positive; know when an edge is dying), not the edge.

## Dead ends (things that did not work, kept visible)

- **Single-factor alpha on mega-caps** — null (efficient-market ceiling on the most-arbitraged names).
- **Naive mean-variance optimization** — error-maximizes; worst drawdown even after shrinkage.
- **BTC/ETH stat-arb** — an in-sample Sharpe of 3.56 collapsed to −0.62 out-of-sample; the "edge" was
  leakage. Reported as a negative result (`run_statarb.py`).
- **"Risk parity wins" as an allocation conclusion** — an early draft; corrected once the gauntlet and
  excess-of-cash returns showed equal-weight and the null are the real story.

## The principle

Report the null. When something looks significant, assume it's the search talking until it survives
out-of-sample, across regimes, and after correcting for the degrees of freedom above. Everything in
this repo is built to make that assumption the default.
