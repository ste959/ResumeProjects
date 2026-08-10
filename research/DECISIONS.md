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

**Mechanical-flow overnight reversal ("Shadow of the Machines", `run_mechflow.py`)**
- A *novel, self-invented* structural idea: leveraged/inverse ETFs must rebalance toward the day's move at
  the close (`k(k-1)·AUM·r`, same direction for all k∉{0,1}); the non-informational overshoot should revert
  overnight, scaling with forced flow ÷ underlying liquidity. Durability thesis: the source (mechanical flow)
  *grows* as markets get passive, so it should resist crowding.
- **Result: mechanism CONFIRMED, thesis REFUTED — the ideal honest arc.** The reversal does scale with
  flow÷liquidity (corr +0.47) and SPY shows ~zero reversal exactly as predicted (too deep to move). But the
  tradable dollar-neutral book is null gross (−0.18, CI includes 0) and dies to 336×/yr cost, and — the key
  find — the decay monitor **disproved my own durability thesis**: the edge worked 2020-22 (+0.61) and decayed
  to −0.91 in 2023-26 (slope t −2.0). Crowding outran the growing source. Inventing an edge is easy; using
  your own tool to disprove it is the job.

**Buyback-blackout regulatory edge ("The Absent Buyer", `run_buyback.py`)**
- A differentiated, self-invented idea: buybacks are the dominant price-insensitive buyer; firms are
  blacked out from repurchasing before earnings, so a stock loses its biggest buyer on a recurring
  schedule. Built point-in-time from SEC-EDGAR (blackout anchored to 10-Q/10-K filing dates; intensity
  from XBRL repurchase facts ÷ market cap).
- **Result: REFUTED, with the confound diagnosed.** The short-in-blackout book is significantly *negative*
  gross (−1.04, HAC t −2.7) and the tercile drag isn't monotonic. The diagnosis is the value: the blackout
  window overlaps the **pre-earnings-announcement drift** (stocks drift up into earnings), which dominates
  and flips the sign; mega-caps are too liquid for buyback absence to move (the same flow÷liquidity gate);
  and the annual-only XBRL intensity read is weak. The refinement it points to: neutralize the earnings
  window and move to mid-caps. Inventing a regulatory edge is rare; diagnosing why the naive test fails is
  the job.

**Vol-control deleveraging ("The Forced Seller", `run_forcedseller.py`)**
- Anticipate the mechanical flow of vol-target funds: exposure = target/realized-vol, so a vol spike forces
  multi-day selling. Built a directional signal from Δexposure and rode it, benchmarked against generic
  vol-timing (Moreira–Muir) and buy-hold.
- **Result: refuted — riding the flow is the WRONG SIGN.** Forced-seller is significantly negative (−0.96,
  HAC t −2.5) and decaying; the forward-return regression is ≈0. After a vol spike the market front-runs and
  **bounces** (mean-reversion + the forced selling being anticipated/absorbed), and that dominates the
  continued deleveraging — you'd fade, not ride. And vol-target-hold (0.80) ≈ buy-hold (0.85) in the bull.

**The cross-study theme (mechflow + buyback + forcedseller) — the real insight:** every self-invented
mechanical-flow edge came back the same way. The *flow* is real and mechanical; the *edge* is not, because
the mechanical actor's trade is the most predictable thing in the market, so it's the most competed-for —
the impact is anticipated, absorbed, and usually reversed before a taker can capture it. A "structural,
can't-be-arbitraged" story still isn't a free lunch: the forced flow pays only the **liquidity provider**
(a maker earning the spread), not a taker riding it. That conclusion is only reachable by building and
honestly testing several — which is what the platform is for.

**Implementation alpha / transfer coefficient ("the capstone", `run_transfer.py`)**
- The thesis the whole project builds toward: the realistic, defensible edge for a junior is raising the
  *transfer coefficient* (Grinold–Kahn: IR = IC·√breadth·TC) — making a signal a desk already trusts
  deployable — not discovering a unicorn. Took cross-sectional 12–1 momentum and layered the industry-
  standard stack (winsor/z, β+vol neutralization, vol-targeting, market-beta hedge, turnover control).
- **Result (honest and strong): implementation is diagnosis + deployability, not Sharpe-manufacturing.**
  Neutralizing β/vol cut the GROSS Sharpe 0.24 → 0.10 — **57% of the raw "alpha" was a hidden factor tilt**,
  the mirage caught before capital is committed. The stack delivered the real wins (market-neutral β
  0.09→0.01, drawdown −16%→−12%) but net Sharpe went 0.20→0.01 because mega-cap momentum (IC 0.02) has no
  real idiosyncratic alpha to transfer — and an honest analysis SAYS SO. The pitch, quantified: make good
  signals better AND catch the fakes; the same stack on a live signal preserves the alpha.

**Paper-fill validation ("closing the loop", `run_paper.py`)**
- Direct answer to both audits' sharpest criticism ("modeled, not measured"): submit real Alpaca paper
  orders, capture the actual fills, and calibrate the modeled cost to reality.
- **Result: the loop is closed and the model is validated (with an honest caveat).** Against real QUOTED
  spreads the ADV-tier model is spot-on for deep names (SPY/IWM/XLE) and under-charges the thinner XLF
  (real 3.5bp vs modeled 1.5). Real paper FILLS came in at 0.83bp round-trip vs 1.07 modeled — but paper
  fills are OPTIMISTIC (fill near mid, no impact/queue; SPY/QQQ filled at ~0), so that's a lower bound; the
  true live cost sits between the quoted spread and the paper fill, and the model brackets it. Positions
  flattened cleanly. Disclosing the paper-fill-optimism caveat is the point — it's the execution-cost
  literacy a desk hires for.

**Long-history, out-of-sample re-test ("20 years + a pre-registered hold-out", `run_longtest.py`)**
- Addresses the two criticisms a senior weights most: the 6-year single regime, and no pristine OOS. Free
  yfinance data extends the flagship allocation study to 2006–2026 (6 regimes incl. the 2008 GFC); the
  methods were fixed on 2020–26, so 2006–2019 is a genuine, pre-registered hold-out.
- **Result — 20 years CHANGES the conclusion, honestly (and it's the strongest honesty artifact yet):**
  (1) min-detectable Sharpe falls ~1.3 → 0.64, so the earlier "everything is null" was an *underpowered*
  artifact; (2) the diversified books now clear the bar (60/40 exSharpe 0.64, t 3.2) — but that's the risk
  PREMIUM, not alpha (all seven allocators cluster at 0.47–0.64, no skill over the premium); (3) the
  pre-registered OOS confirms the premium persists (best clears the bar on 2006–2019, never seen); (4) it
  **partially FALSIFIED my own registered hypothesis** — I predicted 2008 would be the worst regime, but
  60/40 did worse in 2022 (−1.19) than 2008 (−0.75) because 2008 bonds rallied (flight-to-quality) while
  2022 stocks+bonds fell together. Reporting that partial refutation is what pre-registration is for.
- Caveat disclosed: yfinance is survivorship-biased; the point-in-time universe machinery is ready for a
  paid feed.

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
