# Finance for Engineers — a 3-minute primer

This project uses **trading as a problem domain** because it forces genuinely hard software problems:
nanosecond latency, strict correctness invariants, distributed consistency, and large-data research.
**You do not need any finance knowledge to appreciate the engineering** — every domain term below is
mapped to the software concept it really is. If a word in the code or UI is unfamiliar, it's here.

> TL;DR for a hurried reviewer: an *order book* is a priority queue, *matching* is a merge/join,
> an *OMS* is a workflow state machine over a database, and an *alpha signal* is a pure function over a
> time-series. The interesting parts are the engineering around those, not the jargon.

---

## The Exchange — a matching engine

A **market** is a place where buyers and sellers trade one thing (a stock, a coin). The core data
structure is the **order book**.

| Term | Plain English | The software concept |
|---|---|---|
| **Order book** | The live list of all buy and sell offers for one instrument | Two sorted maps (best price first) of FIFO queues — a **priority queue** per side |
| **Bid / Ask** | The best price someone will buy at / sell at | The heads of the two priority queues |
| **Spread** | The gap between bid and ask | `ask − bid` |
| **Matching engine** | Pairs a new order against the best opposite orders | A **merge/join** over the two sorted structures, honoring priority |
| **Price-time priority** | Best price wins; ties broken by who was first | The ordering invariant the engine must never violate |
| **Limit / Market / IOC / FOK / post-only order** | "trade only at ≤ this price" / "trade now at any price" / "fill what you can now, cancel the rest" / "all-or-nothing" / "never take, only rest" | Different **policies** applied at submit time — a small strategy pattern |
| **Self-trade prevention (STP)** | Don't let one participant trade with themselves | A guard in the match loop (and the source of a real *composition* bug we found + fixed) |
| **Market maker** | A bot that continuously quotes both a buy and a sell to earn the spread | An agent that reacts to engine events and posts orders |
| **L2 / L3 market data** | Aggregated depth per price / every individual resting order | Two projections/read-models over the book |

**Why it's interesting as software:** it's a latency-critical, allocation-sensitive concurrent data
structure with hard invariants — benchmarked (JMH) and load-tested for tail latency under contention.

## The Desk — an Order & Execution Management System (OMS)

A **desk** is a team that trades. An **OMS** is the software that manages the lifecycle of their orders.

| Term | Plain English | The software concept |
|---|---|---|
| **OMS** | Tracks each order from creation to done | A **workflow state machine** over a database (`NEW → STAGED → ROUTED → PARTIALLY_FILLED → FILLED`, or `CANCELLED`/`REJECTED`) |
| **Fill / Execution** | A trade that (partly) completes an order | An append to the order's execution list + a state transition |
| **Position** | How much of something you now hold | A running aggregate updated on each fill (with optimistic locking) |
| **Blotter** | The list/table of all orders | A paginated, sorted DB query (where we killed an N+1) |
| **Compliance** | Rules an order must pass before trading (limits, restricted names) | A pluggable pre-trade validation chain |
| **Risk** | How exposed the desk is right now | An aggregate derived from the order-event stream in a separate service |
| **RFQ (request for quote)** | "Hey dealers, what's your price for this bond?" — dealers respond, best wins | A request/response auction with competing responders |
| **Rates desk / curve / DV01 / z-spread** | Pricing bonds off an interest-rate curve and measuring their risk to rate moves | Numerical methods: root-finding (bisection/Newton), interpolation, sensitivities (finite differences) |

**Why it's interesting as software:** a state machine with legal-transition enforcement, event-driven
integration (Kafka + a transactional outbox), and concurrency (optimistic locking, idempotent messaging).

## The Research Lab — signals, backtests, and a compiler

The **quant** side asks: does a rule for when to buy/sell actually make money, or is it noise?

| Term | Plain English | The software concept |
|---|---|---|
| **Alpha signal** | A rule that scores instruments (buy the high scores, sell the low) | A **pure function over a time-series** — and in this project, a *compiled expression* in a small DSL |
| **The DSL** | e.g. `rank(ts_delta(close, 5)) - 0.5*zscore(volume)` | A real **compiler**: lexer → Pratt parser → AST → semantic checks → evaluator lowering to vectorized NumPy |
| **Backtest** | Replay history to see how a signal would have done | A time-loop simulation with a strict **no-look-ahead** invariant (data at time *t* uses only data ≤ *t*) |
| **Walk-forward** | Test on data the rule never "saw" while being built | Train/validate split discipline (like ML cross-validation) |
| **Sharpe ratio** | Return per unit of risk (higher = better risk-adjusted) | A summary statistic — plus overfitting-aware variants (deflated Sharpe, PBO) to avoid fooling yourself |
| **Survivorship bias / point-in-time** | Only studying companies that survived overstates results | A **bitemporal-adjacent** correctness problem: reconstruct exactly the data visible on a past date |

**Why it's interesting as software:** a from-scratch compiler, a content-addressed cache keyed on the
signal's AST hash, a parallel executor, and a validation harness — plus honest statistics (we report
null results instead of p-hacking a "finding").

---

## The one-paragraph version

A trading platform is: a **priority-queue engine** (the exchange) feeding a **workflow state machine over
a database** (the OMS), integrated with a second service through **event streaming with exactly-once-
effective delivery** (Kafka + outbox), alongside a **compiler + cache + parallel executor** for research,
all validated by a **deterministic test harness**. The finance vocabulary is a thin layer over
well-known software problems — which is exactly why it's a good showcase for solving them.
