# Market-Realism Design Log

A backtest is only as honest as its assumptions. Each entry below is an obstacle a naive
"fill at the mid" backtester walks straight into, why it's wrong in real markets, and what
this platform does about it — including what is *deliberately* left for a later phase and
why. The point of this document is to make the reasoning visible, not just the code.

Guiding principle: **when a fill is uncertain, assume the worse one.** Optimistic fill
assumptions are the number-one way a backtest lies to you.

---

## Data capture

**Naive:** sample top-of-book every second and backtest on that.
**Reality:** you cannot reconstruct a fill from top-of-book. A marketable order walks *down*
the book through many levels; a passive order's fill depends on depth and queue at its price.
Both need the full depth and every update, not a 1 Hz snapshot of the best bid/ask.
**What we do:** `L2Recorder` captures the complete event stream — full-depth snapshots,
every incremental level update, and every trade print — to a replayable log. Top-of-book
sampling (`MarketRecorder`) is kept only for the lightweight microstructure research feed.

**Naive:** write each event to disk as it arrives on the feed thread.
**Reality:** disk I/O on the feed's hot path adds latency and, under load, backpressure —
you would be distorting the very data you are trying to record.
**What we do:** the feed thread only formats a line and pushes it onto a lock-free queue;
a separate scheduled task drains the queue to disk. Capture can never stall the feed.

**Naive:** trust one timestamp.
**Reality:** exchange time, your receipt time, and your decision time are three different
clocks, and the gaps between them are where latency lives.
**What we do:** capture rows are stamped with local **receipt** time, kept deliberately
distinct from exchange time. This is the seam the latency model (a later phase) plugs into.

---

## Replay & execution (Phase 1 — spine)

**Naive:** fill the whole order at the arrival mid (or the close).
**Reality:** size moves through the book. A market order sweeps multiple levels at
progressively worse prices — real, measurable slippage.
**What we do:** the replay engine reconstructs the book event-by-event over virtual time and
fills marketable orders by sweeping the *real recorded depth*, so implementation shortfall vs.
arrival mid reflects genuine multi-level slippage. The same execution code (TWAP / POV /
Almgren–Chriss over the `Strategy` seam) runs live and in backtest.

**Naive:** look-ahead — decide using information the strategy could not have had yet.
**Reality:** the future is not knowable at decision time; using it inflates every result.
**What we do:** the strategy is ticked on a virtual-time cadence and only ever sees the book
state reconstructed from events **up to that instant**. Events are replayed in recorded order.

### Deliberately deferred (with reason)

- **Own-order market impact.** Right now our fills sweep the recorded book but do **not**
  remove that liquidity or move future prices — so at large size we would understate impact.
  This is exactly the market-impact / capacity problem, addressed in Phase 3 (temporary +
  permanent impact, and a Sharpe-vs-size capacity curve). Flagged, not hidden.
- **Passive fills, queue position, adverse selection, latency.** Phase 1 only fills takers
  (they consume displayed liquidity). A resting order's fill depends on queue position and is
  adversely selected — modelled in Phase 2.
- **Fees / rebates, borrow / financing.** Maker-taker economics can flip a strategy's sign;
  added in Phase 3.

---

## Realistic fills (Phase 2 — passive fills, queue position, adverse selection)

**Naive:** a resting quote fills the instant a trade prints through its price. (This is
literally what the live engine's maker fill does — it's labelled "optimistic queue.")
**Reality:** you are in a **price-time (FIFO) queue**. When you post a bid, there is already
size resting ahead of you; a sell only reaches *you* after it has cleared everyone in front.
Fill probability depends on queue position, not just price.
**What we do:** on posting, queue-ahead = the size resting *at our own price level*
(`LiveOrderBook.sizeAt`), the traders genuinely in front of us in the FIFO queue. (Using
size at *all* better-or-equal levels would over-state the queue and starve the fill — better
prices trade against incoming flow separately, not ahead of us in our level's queue.) Reaching
trade volume first depletes the queue; only the overflow fills us, up to our size. Re-quoting cancels and re-posts, so it **resets the queue**
(a fresh order joins at the back). Result on real data: an Avellaneda–Stoikov maker quoted
91 times but filled only 6 — the queue gates fills, exactly as it should.

**Naive:** deplete the queue whenever the book size at your level drops.
**Reality:** size drops from both trades *and* cancels; some cancels are ahead of you (you
advance), some behind (you don't). It's genuinely hard to know.
**What we do (conservative):** advance the queue on **reaching trades only**, not on cancels.
This is the pessimistic choice — you fill later and are more exposed — consistent with the
"assume the worse fill" rule. Cancel-based advancement is a later refinement.

**Naive:** a passive fill is free spread capture.
**Reality:** **adverse selection** — your bid tends to fill right before the price drops. The
fill itself is information; you get picked off by someone who knows more.
**What we do:** **markouts** — every fill is revisited at +1s and +10s and its P&L versus the
later mid is recorded. The signatures come out exactly right on recorded data: an aggressive
**taker** shows *negative* markouts (it moves the price and it reverts), while the **maker**
shows *positive* markouts (spread capture) yet still loses on **inventory risk** — the two
sides of market making, separated and measured.

## Latency (Phase 2b — order + cancel)

**Naive:** your order reaches the market instantly and you can pull a stale quote at will.
**Reality:** there is a delay between deciding and your order arriving, and you cannot cancel
instantly — so your old quote lingers and gets run over in fast moves. This is *the* market-
maker risk.
**What we do:** the fill model acts on the quote as it was `latencyMs` ago — one parameter
capturing both order latency (the new quote posts late) and cancel latency (the old one
lingers until it does). The capture's receipt-time stamps make this well-defined. On recorded
data the effect is the textbook latency signature: as latency rises 0 → 500 ms the maker takes
*more* fills (stale quotes sit longer and get hit) but its short-horizon **+1s markout degrades
monotonically** (+0.31 → −0.33 → −0.56 bps) — it is increasingly **adversely selected**, picked
off right before the price moves. The degradation is short-horizon (the +10s markout washes out
with mean reversion), which is precisely where adverse selection lives.

### Deliberately deferred (with reason)

- **Per-order taker arrival latency.** The current model is a single decision-to-market lag,
  which bites the maker (stale quotes) and state-dependent takers. Modelling arrival latency
  for state-*independent* schedules (e.g. a fixed TWAP that ignores the book) needs deferred
  execution and is a further step.

---

## Costs & market impact (Phase 3)

**Naive:** fill at the touch; maybe subtract a flat fee.
**Reality:** you pay to trade, and — crucially — **your own size moves the market.** At small
size, cost is dominated by fees and the spread; at large size, **market impact dominates and
grows super-linearly**, which is what caps how much capital a strategy can deploy.
**What we do:**
- **Fees.** Takers pay a taker fee; makers pay the maker fee or earn a **rebate** (a maker can
  be net-positive on rebates even when gross-flat) and pay **no impact** — they are the ones
  being impacted against. Commissions and regulatory fees (SEC/FINRA on equity sells) are
  modelled as configurable per-notional costs.
- **Market impact** follows the **square-root law**: `cost(bps) = coef · √(participation)`,
  participation = taker size ÷ traded volume, applied on top of the mechanical book-sweep
  slippage the replay already captures.
- **Financing.** Short inventory accrues a borrow rate over the holding period.

This layer answers the honest question raised back in Phase 1 — *"is ~0 bps real?"* — with a
**capacity curve**. Sweeping a TWAP across sizes on ~70 min of recorded BTC:

| order size | raw slippage | fee | impact | **all-in** |
|---|---|---|---|---|
| 1   | −0.6 bps | 5 | 4.9  | **9.9 bps**  |
| 10  | −0.3 bps | 5 | 15.4 | **20.4 bps** |
| 100 | +1.6 bps | 5 | 48.4 | **53.4 bps** |

The raw slippage stays near zero (it conflates spread with drift — the number that *looked*
free). The **all-in cost rises from ~10 to ~53 bps as size scales 100×**, driven by impact.
That curve — where the cost of size eats the edge — is the institutional capacity question.

### Deliberately deferred (with reason)

- **Permanent vs. temporary impact.** A lasting mid shift (information leakage) is folded into
  the single impact coefficient for now; splitting the two is a refinement.
- **Taxes** — the most-overlooked cost of all — get their own layer (lot accounting, wash
  sales, §475(f) MTM vs. retail) so after-tax returns are honest. See Phase 3.5.

---

## Taxes (Phase 3.5 — the most-overlooked cost of all)

**Naive:** subtract a flat rate from profits — or, as almost every backtest does, ignore taxes
entirely.
**Reality:** the tax bill depends on *how* you traded, not just how much you made, and it can
dominate net returns. The nuances that actually matter:
- **Lot selection.** Average cost is wrong for tax; which lots you sell (FIFO / LIFO / **HIFO**)
  changes the realized gain. On a laddered book, HIFO vs. FIFO produced a **10× difference in the
  tax bill** on the same economic position ($7.40 vs. $81.40).
- **Holding period.** Short-term gains (≤ 1 yr) are taxed at the ordinary rate, long-term at a
  lower one — on a $100k gain, **$37k vs. $20k**. Since quant/HFT strategies are almost entirely
  short-term, **turnover carries a direct tax cost.**
- **Wash sales (§1091) vs. crypto.** Sell a *security* at a loss and rebuy within 30 days and the
  loss is **disallowed**; **crypto is property**, so the rule does not apply. Same loss-and-rebuy:
  the equity's $100 loss is disallowed (tax benefit $0) while crypto keeps it (tax benefit $37) —
  a real asymmetry between the asset classes.
- **§475(f) mark-to-market** — the regime a prop firm actually elects: the open book is marked at
  period end, everything is ordinary, and wash sales / long-term treatment don't apply.
**What we do:** a lot-level tax engine (`POST /api/tax`) that ingests a trade sequence and returns
after-tax P&L under a chosen lot method, regime, and rates — so a backtest's fills can be run
through it to reveal the tax drag almost no backtest models.

*Simplifications (documented):* the disallowed wash-sale loss is taken as a current-period hit
rather than carried into the replacement lot's basis; short sales are not lot-matched; capital-loss
netting and carryforward caps are not applied.

---

## Risk management (Phase 4)

Risk is not a number you read off afterwards — it's limits enforced *before and during* trading,
plus an aggregate, factor-level view of what you're actually exposed to.

**Runtime kill-switches.** Naive backtests let a strategy run to the end no matter what. Real
desks have hard limits — a max drawdown, a daily loss stop, an inventory cap — and a breach
**flattens the position and halts.** The backtester enforces them live: an Avellaneda–Stoikov
maker that drifted to a **−$212 loss** (short 1.2 BTC) was, under an $8 max-drawdown limit,
stopped at −$8.5 — flattened to flat and halted — turning the loss into **+$13.** Pre-trade
compliance (which the OMS already had) is only half of risk; runtime risk-off is the other half.

**Aggregate, factor-level risk.** Naive: risk is a list of line items. Reality: it is aggregate
and by factor. The risk engine sums **DV01** across the bond book (reusing the bond math),
separates **rate** risk from **credit/spread** risk, and stresses the book:
- a long-Treasury / long-corporate / short-long-Treasury book showed net **rate DV01 $1,998/bp**
  but **credit DV01 $3,225/bp** — the short Treasury hedges duration but not spread, so credit
  risk exceeds net rate risk. That's exposure you'd miss reading positions one at a time.
- parametric 1-day 95% VaR, **diversified ($28k) vs. undiversified ($39k)** — the diversification
  benefit made explicit.
- scenario stress including a correlated **RISK_OFF** shock (rates rally, equities fall, credit
  widens) — the flight-to-quality tail where the corporate longs bleed straight through the
  Treasury rally.

*Deferred:* per-name key-rate durations and a true covariance matrix (this VaR assumes factor
independence); the de-cointegration / pairs-blowout scenario is represented by the correlated
RISK_OFF shock rather than a strategy-specific spread model.

---

## Market scenario engine — counterfactual replay (overfitting defense)

**Naive:** a backtest on one recorded path proves the strategy works.
**Reality:** it proves the strategy worked *once*, on that exact path. Markets are non-stationary
and the world adapts — the only question that matters is whether an edge survives when conditions
are slightly different.
**What we do:** a counterfactual transform perturbs the recorded L2 stream into a different regime
— scaling volatility, spread and liquidity, imposing a trend, or injecting a shock — while
preserving book structure (the transform is monotonic in price, so bids stay below the mid and
asks above it). The *same* strategy re-runs against the harder/easier world, and a robustness
sweep runs a grid of regimes and reports how it holds up.

The result on the Avellaneda–Stoikov maker is exactly the hidden fragility a single backtest hides:

| regime | net P&L | markout +1s | max drawdown |
|---|---|---|---|
| base (as recorded) | −178 | +0.01 | 321 |
| high vol 2.5× | +106 | −4.5 | 45 |
| **trend +20 bps/min** | **−12,355** | **−62** | **12,397** |

The maker looks marginal at baseline and even *profits* in higher vol (wider quotes capture more),
but a sustained **trend wipes it out ~70×** — it is implicitly **short momentum**, repeatedly run
over on one side and accumulating a losing inventory against the move. No single backtest would
surface that; the scenario sweep makes it explicit. That is the overfitting defense, quantified.

## Synthetic market generation (known-signal ground truth)

**Naive:** validate a model on real data and trust the backtest number.
**Reality:** on real data you cannot separate a genuine edge from a lucky fit — the ground truth is
unknown. **Simulated data with a *planted* signal has known ground truth**, so you can measure whether
a model actually recovers it, and — just as important — whether it hallucinates one where there is none.
**What we do — and an honest caveat about what it proves.** A generator produces a replayable L2 session
whose book imbalance is skewed toward the next mid move (`imbalanceAlpha`) plus idiosyncratic noise, in the
exact capture format. But note the circularity: the feature the model then reads, `imbalance =
(bid−ask)/(bid+ask)`, *is* the planted skew — so "recovering" the signal on the `signal` session is
**tautological**. That test is therefore a **plumbing + false-positive check**, not a modeling result:

| session | injected alpha | measured IC | what it actually proves |
|---|---|---|---|
| noise | 0 | ≈ **0** | the pipeline does NOT hallucinate signal in noise (genuinely valuable) |
| signal | 2.5 | ≈ **+0.9** | the pipeline is leakage-free and wired correctly — *not* that a model finds hidden alpha |

To test **modeling** honestly, `lob.synthetic_latent_panel` provides a **non-circular** ground truth: a
latent AR(1) fair value drives the forward return, and the features are noisy, *indirect* proxies of that
hidden state (never the label). There the model must denoise several weak views, and it earns a **modest IC
(~0.10) below the theoretical ceiling (~0.15)** — real extraction, honestly bounded. The contrast between
the two synthetic modes is the point: the first validates the harness, the second validates the model.

---

## ML research layer (Phase 5 — the quant *researcher*)

**Naive:** train a model, report the in-sample IC or a shuffled-CV R², call it alpha.
**Reality:** the two ways to fool yourself are look-ahead (using information you wouldn't have had) and
cost-blindness (an edge smaller than the spread you must cross to capture it). The research stack
(`research/mds/`, Python: DuckDB + Parquet + sklearn) is built so neither can hide:

- **Leakage-free harness** — features are computed point-in-time from the reconstructed book; labels are
  *forward* returns; validation is **walk-forward** (expanding window, never shuffled). A deterministic
  test proves the lag is what kills a look-ahead signal (cheating Sharpe ≫ honest Sharpe).
- **Model zoo** — Ridge → gradient boosting → small MLP, each scaled on train folds only.
- **Cost-aware verdict** — every signal is charged half-spread + fee per unit turnover; the headline is
  the **gross-vs-net gap**, not the gross number.

Validated on the ground truth above, the pipeline behaves correctly and the honest findings are:

| study | best IC (t-stat) | net-of-cost verdict |
|---|---|---|
| SYNTH noise (α=0) | +0.005 (t≈0.2) | finds nothing — the false-positive check passes, and the IC is *insignificant* as it should be |
| SYNTH signal (α=2.5) | +0.922 (t≈90) | recovers the planted signal — hugely significant — but **dies after spread** at tick frequency |
| REAL BTC-USD microstructure | +0.289 (t≈91) | a real, *strongly significant* predictive signal, yet **untradable** as a taker (fees) *and* as a maker (locked book) — see the maker study below |
| REAL equity momentum (cross-sectional, 123 names, ~5.9y) | — | net +0.56 (best) at low turnover (0.10) — **HAC t ≈ +1.35: not significant** |
| REAL equity risk-adjusted momentum | — | net +0.53, correlated to momentum — **HAC t ≈ +1.26: not significant** |
| REAL equity reversal / sector-rel reversal / VWAP-pressure | — | high-turnover (~0.63) **losers** (net −1.0 to −1.2); two clear |t|>2.89 but are losers, not edges |
| REAL equity low-vol / BAB / idio-vol / MAX | — | all negative, none a positive edge — the low-risk / lottery family |
| REAL equity **sector-relative momentum** (new) | — | net **+0.41** (HAC t +0.98) — see below: this *flipped* from ≈0 on the shorter window |
| REAL equity **order flow** (new — signed-volume vs VWAP, participation trend) | — | flow-pressure is a high-turnover reversal loser (−1.10); participation-trend a mild +0.38, neither significant |

Two lessons the whole layer is built to teach. First, **what survives is low turnover, not high IC** — a
+0.29 IC that trades every tick is worthless; IC is not tradability. Note the discipline in the IC column:
each carries a **t-stat on an overlap-adjusted effective sample** (Fisher-z, `n_eff ≈ n / horizon`, so a
horizon-H label can't fake significance by counting overlapping samples), and the P&L is booked on
**non-overlapping** samples so a persistent position isn't credited the same move H times. The real BTC IC
is *strongly* significant (t≈91) — and still dies after costs: significance confirms the signal is real, it
says nothing about whether you can trade it.

The taker verdict ("dies after spread") only named the next question — *would a **maker** capture it?* —
so the maker study (`run_microstructure.py --maker`, `mds/maker.py`) actually answers it. A passive maker
earns the half-spread on each fill but is **adversely selected** (a resting bid fills precisely as the
price ticks down to it); net per fill = half-spread − adverse selection, measured by markouts. On the real
BTC session (≈3M events, crossed/locked books skipped): the maker earns only **+0.03 bps** of half-spread
and pays **−0.36 bps** of adverse selection → **−0.34 bps/fill**. Using the model's forecast as a *fill
filter*, the fills it endorsed net **−0.20** vs **−0.36** for the ones it warned against (**+0.17 lift**) —
so the signal genuinely **predicts adverse selection** (consistent with its real IC); it just can't be
monetized, because **BTC-USD is an effectively locked 1-tick market with no spread to earn**. The taker
died to fees, the maker dies to a locked book: a real signal with no microstructure edge — a sharper,
truer conclusion than the taker test alone could reach. Second, and more important once we
report **t-stats and confidence intervals** (see `run_crosssec.py`): **no signal clears statistical
significance.** On the **full ~5.9-year window (1491 days — the max the free IEX feed allows; earlier than
2020-07-27 is a hard stop)**, momentum's +0.56 Sharpe still straddles zero (HAC t ≈ 1.35). This is
*computed, not asserted* (`mds/validation.py`): significance uses an **autocorrelation-consistent
Newey–West** t-stat (not a naive IID one) with a **block-bootstrap** CI, and the multiple-testing bar is
applied **symmetrically** — a Bonferroni-corrected **|t| > 2.89 for 13 tests**, to winners *and* losers
alike. No positive signal clears it; two high-turnover **losers** (sector-rel reversal, VWAP-pressure) do,
but losers are not edges. Across the thirteen signals the **Deflated Sharpe** of the best is **≈0.09** (bar
0.95 — after correcting for the tries, ~9% chance its true Sharpe is even positive) and the **PBO** (CPCV)
is **≈0.06**. The walk-forward is **purged and embargoed** so the label can't leak across the train/test
boundary. Reporting these — rather than the positive point estimate — is the discipline.

**Two more QR-motivated signal families, and a timing overlay — all honest nulls.** (1) *Order flow* from the
last unused fields: a daily-bar **OFI proxy** (sign each day's volume by close-vs-VWAP, net it over a week) and
a **participation trend** (smoothed average trade size = volume/#trades). Flow-pressure is another high-turnover
**reversal** loser (−1.10) — daily-bar order flow encodes short-term mean-reversion, un-monetizable at 0.63
turnover; the real OFI edge needs the L2 tape (see the crypto microstructure layer / the data roadmap).
Participation-trend is a mild low-turnover **+0.38** (t 0.98) — the most interesting new positive, still not
significant. (2) A **vol-managed overlay** (Moreira–Muir / Barroso momentum crash-scaling) — scale each signal's
exposure inversely to its trailing realized vol (`run_portfolio.py`). It produces **no consistent lift** and
does not rescue momentum (+0.56 → +0.49) or create significance: these signals have no exploitable vol-timing
structure on this universe/period. Both are the disciplined, documented negatives a QR delivers — real tests,
honest results.

**A finding that flipped — the most honest lesson of all.** The set was expanded (tapping
the previously-unused OHLC/vwap fields): sector-relative momentum, overnight, sector-relative reversal,
close-vs-VWAP pressure, MAX/lottery. On the shorter 4.4-year window, **sector-relative momentum netted ≈0**,
which looked like clean evidence that momentum's edge was pure sector exposure (and neutralization agreed).
Adding just **1.5 more years of data flipped it**: sector-relative momentum is now **+0.41**, and momentum's
β+sector-**neutral** book holds **+0.44** (vs the raw +0.56) — so on the longer sample the edge is *not*
mostly sector exposure. Neither number is significant, and that is the point: **a secondary conclusion
reversed under a modest data change** — exactly what an underpowered, regime-driven null looks like, and the
strongest possible evidence that none of these are durable edges. (The short-horizon signals remain the
biggest-|t| losers at ~0.63 turnover — a real continuation/microstructure effect, un-monetizable at that
turnover.) Widening the family to **thirteen** signals also correctly **deflated the best Deflated Sharpe**
(0.31 → 0.09 as the window grew and more signals were tried) — the honest, automatic cost of more tries.

**Realism, power, and regime — four checks that finish the honest picture** (`run_crosssec.py`):

- **Statistical power.** With ~1238 active days (~5.9y) this sample can only detect (80% power) an
  annualized Sharpe **≳ 1.26** — a function of the return-series *length*, not breadth. Every signal is
  below that. Broadening the universe **40 → 123 names** and extending to the full ~5.9y (the free-feed
  max) did *not* rescue the signal, which points to a genuine null; the remaining data dependency is
  *point-in-time* history with delistings (survivorship is still uncorrected — extending *forward* adds
  none, but a decade of *earlier* history would, and is a hard stop on the free feed).
- **Beta + sector neutralization.** Dollar-neutral alone is a toy; the book is residualized against
  market β and GICS sector, dropping mean |net β| from **0.13 → 0.01**. On the full window momentum's
  neutral book holds **+0.44 (vs raw +0.56)** — most of its edge *survives* neutralization here (the
  opposite of the shorter window; see the "finding that flipped" above).
- **Cost realism (capacity).** Adding a √-law market-impact term (participation vs ADV) and short
  borrow, momentum's net Sharpe goes **+0.56 (frictionless) → +0.11 ($100M book) → −0.84 ($1B)**.
  The edge is not robust to impact, and impact scales with size — the capacity wall, quantified on the
  equity book rather than only in the crypto engine.
- **Regime dependence.** Per-year net Sharpe swings widely (2021 +0.7, 2022 +0.8, 2023 −0.6, 2024 +0.6,
  2025 −0.0, 2026 +1.9);
  one blended number hides that the "signal" is really a few regime bets.

Together these turn "no significant edge" from a p-value into a fully-argued conclusion: underpowered
data (even at the free feed's ~5.9y max), no signal significant after symmetric correction, a secondary
finding that *flips* under 1.5 more years, an apparent edge that dies to realistic impact at size, and no
stability across regimes. That is what an honest research note looks like — and the honesty is the product.

## Portfolio construction (Phase 6 — the quant *trader*)

**Naive:** run mean-variance on the signals' historical returns and trust the optimal weights.
**Reality:** naive Markowitz over-fits the estimated means and blows up out-of-sample; and no optimizer
can create alpha that isn't in the inputs. The allocator (`research/mds/portfolio.py`) is therefore
**walk-forward** (weights fit on a trailing window, applied to the *next* block) and offers equal-weight,
inverse-vol / risk-parity, and **shrunk** max-Sharpe (fixed-intensity λ = 0.3 shrinkage toward a scaled
identity — *not* the analytic Ledoit-Wolf optimum, long-only).

Two honest results, deliberately shown side by side:

- **Machinery works (ground truth):** across four uncorrelated synthetic Sharpe-0.7 signals, walk-forward
  allocation lifts the Sharpe from ~0.8 (avg single) to ~1.6 — the ~√N diversification benefit, pinned by
  a test.
- **Machinery can't rescue bad inputs (real):** allocating across the six equity signals **fails to beat
  the best single one** (best allocation, inverse-vol, −0.40 vs risk-adj-momentum +0.47), because most of
  the signals lose money — and, printed with t-stats, *none* of the allocations is statistically
  distinguishable from zero either. Garbage in, garbage out — the optimizer's value appears only with a
  richer set of *good* signals.

Reporting the second result rather than fishing for a flattering combination is the point. Also included:
vol-targeting (scale to a risk budget) and a Kelly-fraction helper (with the standard caveat that full
Kelly is too aggressive to run).

### Capacity & crowding (Phase 6b — game theory of size and competition)

**Naive:** a backtest Sharpe is the strategy's value.
**Reality:** that Sharpe is measured at *infinitesimal* size. The trader's real questions are how much
capital the alpha absorbs before its own market impact eats it, and how many others are already in the
trade. `research/mds/capacity.py` models both with standard linear-impact (Kyle-λ) machinery:

- **Capacity (own size).** Realised rate falls linearly with deployed capital, `rate(C) = μ − λC`, so
  profit `μC − λC²` is concave and maxes at capacity `C* = μ/2λ`. The profit-maximising allocation is
  therefore **water-filling** across signals (fund each to its own capacity), *not* all-in on the top
  Sharpe. Demo: three signals with equal edge but different impact — concentration earns +0.120,
  capacity-aware +0.155 from the *same* capital.
- **Crowding (others' size).** K players trading the same book is a Cournot game; the symmetric Nash is
  `C* = μ/(λ(K+1))`. As the crowd grows, total capital rises toward `μ/λ` but the shared rate collapses
  toward 0 and **aggregate profit falls monotonically from the monopoly optimum** (0.050 → 0.011 for
  K = 1 → 16) — the tragedy of the commons that makes a crowded factor un-investable.

Read across to the real signals (with λ proxied from turnover — an assumption, flagged), the capacity
allocator funds only the positive-edge signals and refuses the money-losers automatically (`C* < 0`).
It confirms the same honest conclusion one layer up: two 0.83-correlated winners are still one bet.

---

## Bias register — every known simplification and which way it cuts

Naming the *direction* of a bias is the actual skill — a simplification that flatters the
strategy is far more dangerous than one that penalises it. Each item below is an accepted
approximation (not a bug — the bugs were fixed); several are pinned by `biasCallout_*` tests so
they can't drift silently.

| Simplification | Direction of the bias | Where |
|---|---|---|
| Market impact scaled to **whole-session** volume | Not conservative — the same order shows *less* impact on a longer session; the cost floats with session length rather than a real ADV | `BacktestService` impact |
| Kill-switch flatten is **frictionless** | Flatters the kill-switch — real forced liquidation into a drawdown is costly, so realised losses are *understated* exactly when it matters | `BacktestService` flatten |
| Parametric VaR assumes **factor independence** | **Understates** the correlated risk-off tail (rates/equity/credit co-move); overstates the diversification benefit | `RiskEngine`; `biasCallout_varAssumesFactorIndependence` |
| Replay assumes **your orders don't move the market** | Maker P&L assumes the recorded flow is unchanged by your presence — inherent to all historical replay; adverse selection *is* captured via markouts | `BacktestService` maker fills |
| Impact is a **cost overlay**, no permanent accumulation across slices | Understates the cost of large, slow execution | `BacktestService` impact |
| Wash-sale loss taken **in-period**, not carried to the replacement's basis | **Overstates** the wash-sale tax hit (the loss is deferred, not destroyed) | `TaxEngine` |
| Short-term and long-term **not netted** | Can create an artificial tax benefit at different rates | `TaxEngine`; `biasCallout_shortAndLongTermAreNotNetted` |
| §475(f) MTM allowed on **crypto** | Legally contested (crypto is property, not a security) — modelled, not endorsed | `TaxEngine` |
| Oversell (short beyond holdings) drops the excess | Under-reports proceeds; shorts aren't lot-matched | `TaxEngine` |
| Bond pricing: **par yield as discount yield**, 30/360 for Treasuries (should be ACT/ACT) | Small indicative-pricing inaccuracy that grows with curve steepness | `DealerQuoteEngine`, `BondMath` |
| Synthetic imbalance IC ≈ **+0.9** is **tautological** (the feature IS the planted skew) | It validates the *plumbing*, not modeling — a real imbalance IC is ~0.01–0.05. The honest modeling test is the non-circular `synthetic_latent_panel` (model earns ~0.10 vs a ~0.15 ceiling) | `SyntheticMarketGenerator`, `lob.synthetic_latent_panel` |
| Markout horizon drifts long on **sparse** tapes | Biases the adverse-selection metric (not P&L) on thin/synthetic sessions | `BacktestService` markouts |
| Capacity model uses **linear** (Kyle-λ) impact; real impact is concave (√-law) | Over-penalises small size, under-penalises very large — capacity `C*` is indicative, not a number to trade on | `capacity.py` |
| Crowding λ proxied from **turnover**, not measured; crowd assumed **identical** players | The read-across capacities are illustrative; real crowds are heterogeneous and λ needs real ADV/impact data | `capacity.py`, `run_capacity.py` |
| Equity √-law impact coefficient (σ·Y ≈ 2%) is **assumed**, and free-IEX volume **understates** ADV | The cost-sensitivity capacity numbers are directional, not calibrated; understated ADV makes impact *conservative* (over-charged) | `crosssec.py` impact model |
| Sectors are a **static hardcoded** GICS map for the 123 names | Fine for neutralization here, but not point-in-time (a name's sector can change); a real book uses a maintained classification | `alpaca_data.SECTORS` |

### Bugs found by adversarial review and fixed (with regression tests)

An adversarial code review found six real defects that the earlier tests missed — most instructively,
two that *passing* tests were hiding. All fixed, each with a test that would now catch it:
kill-switch re-arming under latency; wash-sale counting the sold lot as its own replacement (and
double-counting replacements); queue-position over-counting via better levels; equal-weighted
markouts; the risk engine reclassifying un-priceable bonds as equity; and a leap-day holding-period
off-by-one.

The review also flagged a convention risk: our fill model assumed a trade's `side` was the
**aggressor**, but Coinbase documents `market_trades` `side` as the **maker** side (the opposite).
Verified against the docs, then made moot — maker fills are now gated purely by **price** (a print
at/above our ask filled our ask), matching the live engine and independent of the feed's side
convention. The lesson: verify the assumption, then design so the answer doesn't matter.

---

*Phases 1–6 span the three-persona lifecycle: the engineer who builds the market and backtester,
the researcher who mines it for signal, and the trader who allocates risk across what survives.
Phase 6b (crowding / capacity decay) and a deep-learning model (DeepLOB, blocked on a torch env)
extend this log next.*
