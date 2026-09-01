# 9. Avro on the wire, behind a Schema Registry

**Status:** Accepted

## Context
The OMS and the risk service are coupled only by the `order-events` Kafka topic. That contract was plain
JSON, hand-maintained as two independent `OrderEvent` types plus a checked-in `contracts/order-event.json`
and a consumer-driven test on each side (ADR-era). It worked, but it left two gaps a real data platform
closes:

- **Nothing mechanically stopped an incompatible change.** The contract test caught drift only for the
  cases it happened to assert; a producer could add, rename, or retype a field and the first sign of
  trouble would be mis-aggregated risk downstream.
- **JSON is untyped and unversioned on the wire** — no enforced field types, no schema id, no evolution
  story beyond "don't break it."

This is exactly the "Schema Management Platform for Protobuf and Avro" problem a data-platform team owns.

## Decision
Make the topic's wire format **Avro, governed by a Confluent Schema Registry**, with the schema as the
single source of truth:

- **One canonical schema** is the contract. Each service keeps a byte-identical copy at
  `src/main/avro/order-event.avsc` — a copy per module so the schema sits inside each Docker build
  context — and both generate their `OrderEventRecord` from it (avro-maven-plugin). The registry (below)
  is what actually prevents drift: a change registered from one service that isn't BACKWARD-compatible
  with the other's copy is rejected at runtime.
  Fields use real types: `enum` for the event type/status (with a `default` symbol for forward tolerance),
  `decimal(19,2)` for notionals (exact, not floating point), and `timestamp-micros` for the event time.
- **Internal model stays separate from the wire.** The OMS keeps its domain `OrderEvent`; a mapper +
  `OrderEventAvroSerializer` convert to Avro only at the serde boundary, so the outbox relay never learns
  about Avro or the registry. The risk service likewise maps the Avro record into its own `OrderEvent`.
- **The registry enforces BACKWARD compatibility.** The serializer registers the schema under
  `order-events-value` and stamps each record with the registered schema id; the consumer resolves each
  record against the registry, so a producer schema newer than the consumer's still reads.
- **CI enforces it too, without infrastructure.** `OrderEventSchemaCompatibilityTest` checks a
  BACKWARD-compatible evolution is accepted, a breaking change (a new required field with no default) is
  rejected, and v1-written data is readable by a v2 consumer — all with pure Avro. A `mock://`-registry
  round-trip test exercises the full serializer→deserializer path (schema id and all) with no broker.

## Consequences
- **Gain:** the contract is a typed, versioned artifact with an enforced compatibility policy — a breaking
  schema change fails the build (and would be refused by the registry) instead of silently corrupting a
  downstream aggregate. Both services derive one identical type from it.
- **Cost:** a code-generation step and two more dependencies per service, plus a real runtime dependency —
  enabling Kafka now also requires a reachable Schema Registry (`SCHEMA_REGISTRY_URL`). The end-to-end
  broker+registry path is exercised in the Dockerized CI lane; unit tests cover everything else via
  `mock://` and pure-Avro compatibility checks.
- `contracts/order-event.json` is retained as a human-readable field reference but is **superseded** by
  the `.avsc` as the enforced contract.
