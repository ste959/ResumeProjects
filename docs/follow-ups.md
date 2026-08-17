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

## 2. Blotter pagination (scale)

**What.** `OrderRepository.findAllByOrderByCreatedAtDesc` (and the status/portfolio variants) return the
entire result set with an `@EntityGraph` collection fetch — fine now, an OOM risk at 100× orders.

**Why deferred.** Pagination changes the controller/service API surface (`Pageable` → `Page<Order>`),
which ripples into the frontend blotter and the existing tests. Worth doing as its own change with the
frontend updated in lockstep, using **keyset** pagination on the new `(status, created_at)` index (added
in `V6__query_indexes.sql`) rather than offset pagination.

**Note.** The supporting indexes are already in place (V6), so the query side is ready; only the API
change remains.

---

Both were surfaced by the audit and are real; they are sequenced after the safe, self-contained fixes
precisely *because* they touch the money path and a public API and deserve dedicated, tested treatment.
