# Effectively-once across a Kafka boundary, without distributed transactions

*A walkthrough of how an order's state change reaches a second service exactly once in effect — and,
more importantly, why each failure mode is safe. The short version: **at-least-once delivery + an
idempotent consumer**, not exactly-once transactions.*

## The problem: the dual write

The order-management service (OMS) has to do two things when an order changes: persist the new state to
Postgres, and publish an `OrderEvent` to Kafka so the risk service can react. The naive approach does
both directly, one after the other. That's a **dual write**, and it has no safe ordering:

- **Commit, then publish** — if the process dies after the DB commit but before the Kafka send, the state
  changed and *no event was ever emitted*. The risk service is now silently wrong, forever.
- **Publish, then commit** — if the send succeeds but the transaction rolls back, a **phantom event**
  describing a state that never happened is loose in the system.

You cannot fix this by being clever about ordering or by adding retries around the send — the failure is
in the *gap between two systems that don't share a transaction*. The only real fixes are (a) a
distributed transaction spanning Postgres and Kafka, or (b) collapsing the two writes into one.

## The design: outbox + relay + idempotent producer + idempotent consumer

I chose (b). Four pieces, each doing one job:

**1. Transactional outbox.** The event is written to an `outbox_event` table **in the same database
transaction** as the order state change. Now there is only one write. Either both the state and the
event commit, or neither does. The phantom-event case is gone by construction: an event exists in the
outbox *if and only if* the state it describes was committed.

**2. A relay drains the outbox to Kafka.** A scheduled `OutboxRelay` polls unpublished rows, sends each
to Kafka keyed by order reference, and stamps `published_at` **only after the broker acknowledges**.
Delivery is therefore **at-least-once**: if the process dies after the send but before the stamp, the row
still looks unpublished and is sent again next tick.

**3. An idempotent, keyed producer.** The producer runs with `enable.idempotence=true`, `acks=all`, and
every event keyed by `orderRef`. Two consequences:
- All events for one order land on **one partition, in order**, and the idempotent producer preserves
  that order across its own internal retries (it won't reorder or duplicate a *retried* send within a
  session).
- A transient broker blip during a send is retried safely by the producer itself.

**4. An idempotent consumer.** The risk service aggregates each order's contribution from its state in a
way that is **convergent under redelivery** — reprocessing the same or a stale event doesn't double-count;
it lands on the same answer. This is the piece that actually closes the loop, and it's worth being precise
about *why*.

## Why each failure mode is safe

- **Crash between DB commit and publish** → the event is already durably in the outbox (same
  transaction), so the relay sends it on the next tick. **No loss.** This is the case the naive dual
  write gets wrong.
- **Rollback after a "phantom" publish** → impossible: nothing is published until the relay reads a
  *committed* outbox row. **No phantoms.**
- **Send succeeds, crash before `published_at` is stamped** → next tick re-sends the row. The event
  reaches the topic **twice**. Here's the subtle part most write-ups get wrong: the idempotent producer
  does **not** save you here — it only de-duplicates retries *within one producer session/epoch*, and a
  relay restart is a new session, so the broker sees a genuinely new record. The duplicate is real on the
  wire. What makes it harmless is **the consumer**, not the producer: convergent, latest-state-per-order
  aggregation means processing that duplicate produces the same result. **Duplicate delivered, but
  effectively-once in outcome.**
- **A permanently bad row** (unserializable payload, or a send that keeps failing) → it is
  **dead-lettered** after bounded retries instead of parking at the head of the queue and starving every
  later event. One poison row can't wedge the stream.
- **Ordering** → because events are keyed by `orderRef`, an order's lifecycle stays on one partition in
  order, so the consumer never sees `FILLED` before `ROUTED` for the same order.

## What "effectively-once" honestly means here

It is **at-least-once delivery composed with an idempotent consumer** — not exactly-once. That
composition is deliberate. Kafka *can* do exactly-once with transactions spanning the read-process-write
cycle, but coordinating that across Postgres and Kafka is heavier, and it buys nothing here: an idempotent
consumer is simple, local, and turns "at-least-once" into "exactly-once in effect" for free. The cost I
accepted in return is **latency** — events are published on the relay's tick, not the instant the
transaction commits — and the operational surface of a relay, a retention purge, and a dead-letter path
(all built). For order state, never losing an event is worth a few milliseconds of publish latency.

## Where it lives

- `backend/.../oms/event/OutboxRelay.java` — the relay (pipelined sends, ack-then-mark, dead-lettering,
  retention purge).
- `backend/.../oms/event/KafkaProducerConfig.java` — the idempotent, keyed, Avro producer.
- `risk-service/.../OrderEventListener.java` + the aggregator — the idempotent consumer.
- [ADR-0001](../adr/0001-transactional-outbox.md) — the decision record, including the exactly-once
  alternative and why it was rejected.
