# Risk Service (Java 21 · Spring Boot · Kafka)

A small, independent microservice that maintains a **live desk-risk view** from the OMS order-event
stream — the consumer half of the platform's event-driven architecture.

## What it does

- Subscribes to the `order-events` Kafka topic (`OrderEventListener`).
- Keeps only the **latest event per order** (`RiskAggregator`, a `ConcurrentHashMap`) and derives all
  aggregates from current state — so consumption is **idempotent** and replay-safe.
- Serves the aggregated view over REST (`RiskController` → `GET /api/risk/summary`).

## Reliability

- `ErrorHandlingDeserializer` + a `DefaultErrorHandler` with a **dead-letter recoverer**: a poison
  record is retried a few times, then parked on `order-events.DLT` while the stream keeps flowing
  (`KafkaErrorHandlingConfig`).
- Consumer `concurrency` > 1 (one partition per thread preserves per-key ordering).
- Its own `OrderEvent` record — coupled to the producer only by the shared **Avro schema**
  (`src/main/avro/order-event.avsc`, byte-identical to the OMS copy), whose backward compatibility the Schema Registry enforces;
  `OrderEventContractTest` checks the mapping from the Avro record into this service's own model.

## Run / test

```bash
./mvnw -B verify
./mvnw spring-boot:run    # needs a Kafka broker (see repo-root docker-compose.yml)
```
