# Systematic Equity Research Note
### Cross-sectional factors on US mega-caps: an honest null, and the case for construction over signal discovery

*Desk research note · price/volume + fundamentals + macro/options overlays · 2020–2026*

---

## Summary

Across **18 classic cross-sectional factors** tested on **123 US mega-caps over ~5.9 years**, under a
leakage-free, cost-aware, overfitting-adjusted framework, **no single factor is statistically
distinguishable from zero** once multiple-testing is accounted for. The best factor has a Deflated
Sharpe of **0.08** (a defensible edge needs > 0.95) and no factor clears a Bonferroni-corrected
`|t| > 2.9`. This is not a failure of technique — the validation stack is deliberately conservative —
it is the **efficient-market ceiling on the most-arbitraged names with the weakest freely-available
data**, compounded by a hard **breadth** constraint (Grinold–Kahn: `IR ≈ IC·√breadth`; 123 names is
a handful of independent bets).

The tractable edge, therefore, is not a cleverer signal — it is **portfolio construction and risk
management**, which we show deliver real risk-adjusted value *independent of any significant
standalone alpha*: a factor-neutral, turnover-capped optimizer that carries the same weak composite
alpha at **one-third the drawdown and one-tenth the turnover**; a credit/VIX regime overlay that
**halves a directional book's max drawdown**; and HIFO tax management worth **~170 bps/yr** after-tax
on a $1M book. The path to genuine *alpha* runs through **better data** (survivorship-free breadth,
options history, order flow) and **microstructure**, not more price factors — which is where the
next phase of this work is pointed.

---

## 1. Universe & data

| | |
|---|---|
| **Universe** | 123 US mega-caps across 11 GICS sectors |
| **Sample** | 1,491 trading days, 2020-07-27 → 2026-07-02 (~5.9y — the free IEX feed's hard limit) |
| **Price/volume** | Daily OHLCV + VWAP + trade count (Alpaca/IEX) |
| **Fundamentals** | SEC EDGAR XBRL, **point-in-time by filing date** (not period-end), TTM flows |
| **Macro** | FRED credit OAS (HY/IG) + VIX, causal (shifted 1 day) |
| **Options** | Alpaca live IV surface (snapshot; historical bars are OPRA-gated) |

**Known limitations, stated up front.** The universe is **survivorship-selected** with no
point-in-time membership or delisting returns — every backtest here is therefore *upward*-biased, and
a real study requires a delisting-inclusive source (CRSP / Shardar). ~5.9y is a short sample: a power
analysis (below) shows it can only reliably resolve an annualized Sharpe above **~1.3**. These caveats
sharpen, rather than undermine, the null result: the effects we cannot find are the ones a *favorably*
biased, mega-cap sample should find most easily.

---

## 2. Methodology — the validation framework

Every factor is traded as a **dollar-neutral, unit-gross** book and evaluated identically. The
framework is designed to *catch itself out*:

- **No look-ahead.** A signal formed from data through day *t* is traded into the *t→t+1* return
  (one-period execution lag); missing names are excluded from that day's cross-section, never
  forward-filled to a fabricated price.
- **Realistic costs.** Turnover charged at half-spread + fee; optional √-law **market impact**
  (Kyle-λ, participation = trade$/ADV$) and **short-borrow** financing on the short leg.
- **Neutralization.** Weights residualized against **market β and GICS sector dummies**, so a
  factor's apparent edge cannot be uncompensated β or sector exposure (which explained most of raw
  momentum's naïve Sharpe).
- **Autocorrelation-consistent significance.** **Newey–West (HAC)** Sharpe *t*-stat — overlapping-
  window signals are serially correlated, which inflates the naïve *t*.
- **Distribution-free confidence.** Moving-block **bootstrap** 95% CI for the annualized Sharpe.
- **Selection-adjusted significance.** **Deflated Sharpe Ratio** (Bailey–López de Prado) — the
  probability the true Sharpe is positive *after* correcting for skew/kurtosis and for the expected
  maximum of *N* trials — and **PBO** (probability of backtest overfitting) via combinatorially-
  symmetric cross-validation.
- **Symmetric multiple testing.** A Bonferroni bar over all *N=18* factors, applied to winners **and**
  losers alike (a "significant" loser is just as much a selection artifact).
- **Power.** The minimum Sharpe the sample could detect at 80% power, as the honest counterweight to
  a short, biased sample.

This is the bar. It is not negotiable per factor, and new data does not get a lower one.

---

## 3. Results — the factor zoo is null

The 18 factors span the standard taxonomy: **momentum** (12–1, risk-adjusted, sector-relative,
overnight), **reversal** (short-term, sector-relative, VWAP-pressure), **low-risk** (low-vol, BAB,
idio-vol, anti-lottery), daily-bar **order-flow** proxies (signed-volume, participation trend), and
**fundamentals** (earnings yield, gross profitability, ROE, accruals, asset growth).

**Headline results (β+sector-neutral, net of 5 bps):**

- The single best factor is **value (earnings yield)**, net Sharpe **+0.64**, HAC *t* ≈ **1.6** — the
  economically sensible winner, but **below the significance bar**.
- On a daily-Sharpe basis the selection-best is **momentum**, with a **Deflated Sharpe of 0.08**
  (needs > 0.95) and **PBO ≈ 0.06**.
- **No factor — winner or loser — clears the Bonferroni bar `|t| > 2.9`.** Even the naïvely
  "significant" short-term reversal is a costed, high-turnover artifact, not an exploitable effect.
- **Power:** with this sample length the study can only detect a Sharpe above ~**1.3** at 80% power.
  Every observed |Sharpe| sits well below that — the null is "too little signal in too little data,"
  and it *held* when the universe was widened from 40 to 123 names (Sharpe/DSR ~unchanged), which
  points to a genuine null rather than mere low breadth.

**Interpretation.** Mega-caps are the most-arbitraged, most-efficiently-priced names on earth, and
23 quarterly filings per name over ~6y is too short and too selected to resolve the fundamental
premia (value/quality) that *do* survive in the literature — which live disproportionately in the
small/mid-cap universe where limits-to-arbitrage bind. The technique is sound; the **data is the
binding constraint.**

---

## 4. Results — construction delivers what signals don't

If no single signal clears the bar, the systematic-equity move is to stop hunting one and build a
*portfolio* from the many weak ones. Five layers, each measured against a naïve baseline:

| Layer | Mechanism | Result vs. baseline |
|---|---|---|
| **Multi-factor composite** | Blend value/quality/momentum into one z-scored book | IC *t* **+3.4** (a significant combined *forecast*), yet neutral Sharpe **+0.31 < +0.64** best single — combining cuts noise, it cannot conjure absent alpha |
| **Factor risk model + optimizer** | Barra-style `Σ = BFBᵀ+D`; analytic factor-neutral mean-variance with a 5% position cap and turnover budget | Same alpha at **Sharpe +0.31 → +0.54**, **turnover 0.09 → 0.01**, **max DD −7.7% → −3.9%**, `|net β| ≈ 0.01` — the *investable* form |
| **Regime timing** | Scale exposure on the causal FRED credit-spread / VIX state | Directional book **max DD −22.8% → −10.1%** (HAC *t* 2.4); the neutral book barely moves — drawdown control, not new alpha |
| **Options structuring** | Tail hedge + covered-call overwrite sized off the live IV surface | Variance premium (IV>RV) on **74/123** names; tail hedge ~**3.7%/yr**; overwriting harvests the VRP where it's richest |
| **Tax-aware rebalancing** | HIFO lot selection, wash-sale-safe, LT/ST holding periods | **~$17k / $1M saved** vs. FIFO on identical trades (deferral + long-term-rate conversion) |

**The through-line:** none of these layers needs a statistically-significant standalone signal to add
value. When alpha is scarce, **construction and risk control *are* the edge** — and they are the parts
of the job a short, biased sample cannot invalidate.

---

## 5. Risk & capacity

A backtest Sharpe is measured at infinitesimal size. Two effects bound the deployable book:

- **Capacity (own impact).** With linear (Kyle-λ) impact, profit `μC − λC²` is concave and maximized
  at `C* = μ/2λ`; the profit-maximizing allocation is **water-filling** each signal to its own
  capacity, not all-in on the top Sharpe.
- **Crowding (others' impact).** *K* players sharing a signal is a Cournot game with symmetric
  equilibrium `C* = μ/(λ(K+1))`: aggregate profit **falls monotonically** from the monopoly optimum
  as the crowd grows — the mechanism behind "this factor is crowded."

On this universe these are moot (there is no edge to size), but they are the correct lens for the
data-upgrade agenda below, where capacity — not raw Sharpe — will be the binding constraint.

---

## 6. Strategy suggestions — the research agenda

The next unit of research effort should buy **better data and different market structure, not more
price factors.** Ranked by expected value ÷ effort:

1. **Breadth: survivorship-free small/mid-cap universe.** *The direct fix for the §3 null.* Value,
   quality and low-vol are *stronger* where limits-to-arbitrage bind, and only measurable on a
   point-in-time, delisting-inclusive universe (CRSP via WRDS, or Sharadar/Nasdaq Data Link). Raises
   both breadth (the Fundamental-Law numerator) and the regime where the premia actually pay.

2. **Microstructure & order flow (crypto L2).** *The highest-conviction place genuine, freely-
   observable inefficiency lives.* Daily-bar order-flow proxies already hint at it; the real signals
   need L2: **Order-Flow Imbalance** (Cont–Kukanov–Stoikov — the single best short-horizon
   predictor), **VPIN** (flow toxicity / adverse selection), **queue/microprice dynamics** (Stoikov
   fair value), and **cross-venue lead-lag** (Hasbrouck information share — monetizable when the
   lagging venue's spread is wide enough to capture). This is a different, execution-adjacent game
   with small capacity but *real* edge, and it reuses the existing live-feed and matching
   infrastructure. **It is the focus of the companion execution/matching demo.**

3. **Options-implied signals (forward-looking).** The one dataset that isn't a lagged function of
   price: the **variance risk premium** (sell vol when IV ≫ RV), **25Δ skew** as crash-risk/sentiment,
   the **IV term structure**, and cross-sectional **IV−RV**. Live surface is built; a historical
   study needs an OPRA agreement or an accumulated snapshot tape.

4. **Fundamental depth on a broad universe.** Beyond static ratios: **post-earnings-announcement
   drift / SUE** (one of the most robust anomalies, buildable from EDGAR's realized earnings history),
   **quality composites** (Piotroski F-score, Novy-Marx gross profitability, QMJ), **net issuance**,
   and **accruals** — deployed where §1's breadth constraint is relieved.

5. **Cross-asset / macro factor timing.** Condition the factor *mix* on the credit regime and yield-
   curve slope (value vs. momentum leadership rotates with the cycle); overlay VRP once options
   history lands. Fragile out-of-sample, so held to the same DSR/PBO bar — but the exposure-timing
   half already demonstrably controls drawdown.

6. **Productionize the construction stack.** The multi-factor risk model, constrained optimizer,
   regime overlay, tail-hedging and tax-aware rebalancing already add value on weak inputs; hardening
   them into the medium-term book is low-variance, high-certainty work that compounds whatever alpha
   items 1–5 surface.

---

## 7. Conclusion

The rigorous, honest answer is a **null**: on the easiest names with the weakest data, systematic
price/fundamental factors do not beat the efficient-market prior once you refuse to fool yourself.
Reporting that — rather than a cherry-picked in-sample Sharpe — is the point, and it is the finding a
serious desk would want surfaced. The *value* created here is twofold: a **validation framework** that
makes any future positive result believable, and a **construction layer** that turns weak signals into
an investable, risk-controlled, after-tax book. The next dollar of research is best spent on
**breadth, microstructure, and options data** — and on the execution/market-microstructure work where
the inefficiency is genuinely capturable.

---

*Reproducible: every figure above is computed (not asserted) by the `research/` layer —
`run_crosssec.py` (factor zoo + DSR/PBO), `run_construction.py` (the five-layer stack),
`run_macro.py` (regime overlay), `run_options.py` (IV surface). Validation lives in
`mds/validation.py`; the data-upgrade agenda in `ALPHA-DATA-ROADMAP.md`.*
