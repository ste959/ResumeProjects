# OMS Backend (Java 21 · Spring Boot)

The core service: a **price-time-priority matching engine**, an **order & execution management system**
for bonds, a **rates dealing desk**, and the **event publisher** that feeds the risk service over Kafka.
REST + WebSocket APIs front it; PostgreSQL (Flyway-managed) persists it.

## Package map (`com.bonddesk`)

| Package | What lives there |
|---|---|
| `exchange` | The standalone, JMH-benchmarked **reference matching engine** (CLOB + market maker) — integer ticks, full exchange semantics (IOC/FOK/post-only/STP/replace, L2/L3). |
| `oms.matching` | The **OMS-integrated desk crosser** (`OrderBook` + `MatchingService`) wired into the JPA order/fill lifecycle. *(Two order books on purpose — see below.)* |
| `oms.service` | Order lifecycle, position keeping, execution routing (`OrderService`, `PositionService`). |
| `oms.event` | The **transactional outbox**: `OutboxOrderEventPublisher` writes events in-transaction; `OutboxRelay` drains them to Kafka. |
| `rates` | Rates desk — curve bootstrap, z-spread pricing, DV01/key-rate DV01, multi-dealer RFQ. |
| `pricing` | Bond price/yield analytics off a settlement date (distinct from `rates` curve math). |
| `compliance`, `risk`, `tax` | Pre-trade compliance, aggregate risk breaker, tax lots. |
| `controller`, `dto` | REST/WebSocket endpoints and their request/response shapes. |
| `domain`, `repository` | JPA entities and Spring Data repositories. |
| `equities`, `market`, `strategy`, `execution`, `backtest` | Live Alpaca/Coinbase feeds, market-data streaming, strategy runners, execution/TCA. |
| `observability`, `config` | Correlation-id logging, health, OpenAPI, security, WebSocket config. |

## Two order books, on purpose

`exchange.OrderBook` and `oms.matching.OrderBook` share the TreeMap-of-FIFO design but are **not
duplicates**: the former is the standalone, allocation-light **reference engine** behind the crypto
exchange (benchmarked at ~8M ops/s single-thread); the latter is the **OMS-integrated crosser** for BigDecimal-priced
desk orders inside the JPA lifecycle. Each class Javadoc cross-references the other.

## Order lifecycle

`NEW → STAGED → ROUTED → PARTIALLY_FILLED → FILLED` (or `CANCELLED` / `REJECTED`), enforced by a
legal-transition state machine, with `@Version` optimistic locking. Every transition publishes an
`OrderEvent` through the outbox → Kafka → risk service.

## Performance

Two complementary measurements of the matching path:

- **Single-thread microbenchmark** (`OrderBookJmhBenchmark`, JMH) — ~8M ops/s, 193 B/op, sub-microsecond
  p50 (`make bench`; committed run in `docs/benchmarks/matching-jmh.txt`).
- **Concurrent load / soak test** (`OrderPathLoadTest`) — drives sustained, saturating load from many
  client threads across many books (mirroring the per-book locking of `MatchingService`) and reports
  throughput and **tail latency under contention** at each thread count:

  | threads | throughput/s | p50 | p99 | p99.9 |
  |--:|--:|--:|--:|--:|
  | 1 | ~2.0M | 295 ns | 0.9 µs | 8 µs |
  | 2 | ~3.2M | 395 ns | 1.2 µs | 17 µs |
  | 4 | ~5.0M | 471 ns | 1.6 µs | 7 µs |
  | 8 | ~5.1M | 754 ns | 6.0 µs | 116 µs |

  The honest finding: throughput scales to ~4 threads, then **flattens while tail latency degrades** —
  per-book lock contention and memory bandwidth, not more cores, become the limit. (Laptop-class CPU,
  JDK 21; numbers vary by machine. This isolates the matching core — the full persistence path is
  DB-bound, tracked in `docs/follow-ups.md`.) The harness runs a short version of this as a
  **performance gate** (`matching_load_gate`, asserting throughput and p99 stay within bounds).

  Reproduce: `make loadtest` (or `java -cp target/test-classes:target/classes
  com.bonddesk.exchange.OrderPathLoadTest 2000 16`).

## Run / test

```bash
./mvnw -B verify                 # unit + Testcontainers integration tests (needs Docker)
./mvnw spring-boot:run           # dev (H2 in-memory)
./mvnw spring-boot:run -Dspring-boot.run.profiles=postgres   # Postgres + Flyway
```

See the repo-root `README.md` for the full architecture and `ENGINEERING.md` for the engineering
narrative.
