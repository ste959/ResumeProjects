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
**What we do:** on posting, queue-ahead = total size at prices at least as good as ours
(`LiveOrderBook.sizeAtOrBetter`). Reaching trade volume first depletes the queue; only the
overflow fills us, up to our size. Re-quoting cancels and re-posts, so it **resets the queue**
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
**What we do:** a generator produces a replayable L2 session from a model whose book imbalance is skewed
toward the next mid move with a configurable strength (`imbalanceAlpha`), plus idiosyncratic noise.
Output uses the exact capture format, so a synthetic market is a first-class session. Verified by
recovering the imbalance→forward-return information coefficient from the raw generated book:

| session | injected alpha | recovered IC |
|---|---|---|
| signal | 2.5 | **+0.86** (recoverable) |
| noise | 0 | **−0.02** (varies but predicts nothing — the false-positive check) |

This is precisely how JS validates ML on simulated data, and it is the substrate the ML phase trains
on: fit where the answer is known, *then* turn the model loose on the real feed.

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

| study | best IC | net-of-cost verdict |
|---|---|---|
| SYNTH noise (α=0) | +0.005 | finds nothing — the false-positive check passes |
| SYNTH signal (α=2.5) | +0.922 | recovers the planted signal, but **dies after spread** at tick frequency |
| REAL BTC-USD microstructure | +0.287 | real predictive signal, but **dies after spread** — bid-ask bounce, not tradable |
| REAL equity momentum (cross-sectional) | — | **survives** net +0.36 Sharpe at low turnover (0.08) |
| REAL equity risk-adjusted momentum | — | **survives** net +0.40 — a cleaner momentum, but 0.83-correlated to it (a refinement, not a new bet) |
| REAL equity reversal | — | **dies** — bleeds to costs at 0.62 turnover |
| REAL equity low-vol / betting-against-beta / idio-vol | — | **die** here (net −0.19 to −0.39) — the low-risk family, and all three are 0.85+ correlated to each other (one bet in three costumes) |

The lesson the whole layer is built to teach: **what survives is low turnover, not high IC.** A +0.29 IC
that trades every tick is worthless; a weak monthly signal can be a business. IC is not tradability.

A second lesson emerges from *expanding* the signal set (six price/volume-only factors — no
fundamentals in the free feed, so no true value/quality). The low-risk family (low-vol, BAB, idio-vol)
is beautifully *orthogonal* to momentum (P&L correlation ≈ 0) — exactly what a portfolio wants — **but
loses money** on this 2020–2024 mega-cap universe, a regime where high-beta growth dominated and the
low-risk anomaly reversed. Orthogonal-but-unprofitable is not a diversifier. So even with six signals we
still hold effectively **one bet** (momentum, in two correlated flavours), which is why the Phase 6
optimizer can't beat it. Testing six also inflates the best in-sample Sharpe by multiple comparison —
survivors are candidates, not conclusions. Reporting that, rather than fishing for a flattering combo,
is the discipline.

## Portfolio construction (Phase 6 — the quant *trader*)

**Naive:** run mean-variance on the signals' historical returns and trust the optimal weights.
**Reality:** naive Markowitz over-fits the estimated means and blows up out-of-sample; and no optimizer
can create alpha that isn't in the inputs. The allocator (`research/mds/portfolio.py`) is therefore
**walk-forward** (weights fit on a trailing window, applied to the *next* block) and offers equal-weight,
inverse-vol / risk-parity, and **shrunk** max-Sharpe (Ledoit-Wolf-style covariance shrinkage, long-only).

Two honest results, deliberately shown side by side:

- **Machinery works (ground truth):** across four uncorrelated synthetic Sharpe-0.7 signals, walk-forward
  allocation lifts the Sharpe from ~0.8 (avg single) to ~1.6 — the ~√N diversification benefit, pinned by
  a test.
- **Machinery can't rescue bad inputs (real):** allocating across the three equity signals **fails to beat
  momentum alone** (best allocation −0.48 vs momentum +0.36), because two of the three lose money.
  Garbage in, garbage out — the optimizer's value appears only with a richer set of *good* signals.

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
| Synthetic imbalance IC ≈ **+0.86** | Idealised — real order-book imbalance predicts with IC ~0.01–0.05; a model getting 0.03 on real data is a *win*, not a failure | `SyntheticMarketGenerator` |
| Markout horizon drifts long on **sparse** tapes | Biases the adverse-selection metric (not P&L) on thin/synthetic sessions | `BacktestService` markouts |
| Capacity model uses **linear** (Kyle-λ) impact; real impact is concave (√-law) | Over-penalises small size, under-penalises very large — capacity `C*` is indicative, not a number to trade on | `capacity.py` |
| Crowding λ proxied from **turnover**, not measured; crowd assumed **identical** players | The read-across capacities are illustrative; real crowds are heterogeneous and λ needs real ADV/impact data | `capacity.py`, `run_capacity.py` |

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
