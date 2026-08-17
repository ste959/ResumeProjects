# 1. Transactional outbox instead of a dual write to Kafka

**Status:** Accepted

## Context
The OMS must persist an order change to Postgres *and* publish an `OrderEvent` to Kafka. Doing both
directly is a dual write: if the process dies between the DB commit and the Kafka send, the event is
lost; if the send happens before the commit and the transaction rolls back, a phantom event escapes.
Neither is acceptable for order state.

## Decision
Write the event to an `outbox_event` table **in the same database transaction** as the order change, so
the event and the state it describes commit or roll back atomically. A separate scheduled `OutboxRelay`
drains the table to Kafka and stamps `published_at` only after the broker acks. Delivery is
**at-least-once**; the idempotent producer (keyed by order ref) plus the consumer's latest-event-per-key
aggregation make redelivery harmless. Poison rows are dead-lettered; a retention job bounds the table.

## Consequences
- **Gain:** no lost or phantom events; the write path stays a single local transaction.
- **Cost:** events are eventually (not instantly) published — the relay adds latency; the outbox table
  needs a relay, a purge, and dead-letter handling (all built).
- **Alternative rejected:** Kafka transactions / exactly-once across the DB and broker — heavier, and
  at-least-once + idempotent consumption is simpler and sufficient here.
