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

*Phases 4–6 extend this log as each realism layer lands.*
