# Tracked follow-ups

Improvements identified in the senior-SWE audit that are **deliberately deferred** rather than rushed,
with the reasoning. Keeping this list is the honest alternative to either doing everything half-well or
pretending the gaps don't exist.

## 1. Batch fill persistence per submit (throughput)

**What.** A single incoming order that sweeps N resting price levels currently persists N separate
`@Transactional` `recordFill` calls (`OrderService.recordFill`, fanned out from `MatchingService`). The
in-memory match is fast; the DB round-trips are the real matching ceiling under load.

**Why deferred.** This is the order-money path. Correct batching means collecting the fills produced by
one `submit`, applying them as one transaction (one order save + one position update per touched
security + one outbox row per event) while preserving the existing state-machine transitions, fill
accounting, and optimistic-locking semantics — and re-verifying it against the Postgres integration
tests. That is a careful, well-tested change, not a tail-of-session edit. Doing it badly would be worse
than the current honest throughput ceiling.

**Scope when taken.** New `recordFills(order, List<Fill>)` path; single transaction; keep the
`FillRecorder` retry/dead-letter behavior; add integration tests asserting N-level sweeps produce one
transaction and identical final state.

## 2. Blotter pagination (scale) — ✅ SHIPPED

**What it was.** `GET /api/orders` returned the entire result set with an `@EntityGraph` collection fetch
— fine at demo size, an OOM risk at 100× orders.

**Done** (commit `ee06845`). Replaced with **keyset** (cursor) pagination on the `(status, created_at)`
index from `V6`: `OrderController.list` now returns a `PagedResponse<OrderSummaryResponse>` with an opaque
cursor, the summary rows drop the per-fill collection so the page query fetches only the to-one security
(the `LIMIT` is a real SQL limit, not an in-memory slice), and the frontend was updated in lockstep.
Verified by `OrderRepositoryKeysetTest` (real DB, `@DataJpaTest`) and `CursorTest`. See ADR — the change
went in with tests, not as a tail-of-session edit.

---

Item 1 (fill batching) is the remaining open follow-up; it is deliberately unrushed *because* it touches
the order-money path and deserves dedicated, tested treatment. Item 2 above is done.
