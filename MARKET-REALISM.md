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

### Deliberately deferred (with reason)

- **Latency** (order + cancel) — the book moves between your decision and your order's
  arrival, and you cannot pull a stale quote instantly (you get run over in fast moves).
  The capture is already receipt-time stamped for this; the model is the next increment.

---

*Phases 3–6 extend this log as each realism layer lands.*
