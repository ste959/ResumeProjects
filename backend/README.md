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
exchange (benchmarked at ~3M ord/s); the latter is the **OMS-integrated crosser** for BigDecimal-priced
desk orders inside the JPA lifecycle. Each class Javadoc cross-references the other.

## Order lifecycle

`NEW → STAGED → ROUTED → PARTIALLY_FILLED → FILLED` (or `CANCELLED` / `REJECTED`), enforced by a
legal-transition state machine, with `@Version` optimistic locking. Every transition publishes an
`OrderEvent` through the outbox → Kafka → risk service.

## Run / test

```bash
./mvnw -B verify                 # unit + Testcontainers integration tests (needs Docker)
./mvnw spring-boot:run           # dev (H2 in-memory)
./mvnw spring-boot:run -Dspring-boot.run.profiles=postgres   # Postgres + Flyway
```

See the repo-root `README.md` for the full architecture and `ENGINEERING.md` for the engineering
narrative.
