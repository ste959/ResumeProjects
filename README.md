# Fixed Income Trading Platform

> **BondDesk OMS** — a full-stack, event-driven Order & Execution Management System for bonds.

[![CI](https://github.com/ste959/FixedIncomeTradingPlatform/actions/workflows/ci.yml/badge.svg)](https://github.com/ste959/FixedIncomeTradingPlatform/actions/workflows/ci.yml)
![Java 21](https://img.shields.io/badge/Java-21-orange)
![Spring Boot 3.3](https://img.shields.io/badge/Spring%20Boot-3.3-6DB33F)
![React 18](https://img.shields.io/badge/React-18-61DAFB)
![TypeScript 5](https://img.shields.io/badge/TypeScript-5-3178C6)
![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-event--driven-231F20)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![Kubernetes](https://img.shields.io/badge/Kubernetes-manifests-326CE5)
![Tests](https://img.shields.io/badge/tests-150%2B%20passing-brightgreen)
![Matching engine](https://img.shields.io/badge/matching%20engine-3.3M%20ord%2Fs-blueviolet)

A full-stack, event-driven **Order & Execution Management System (OEMS)** for trading
fixed-income instruments (bonds), built to mirror the engineering surface of a Charles
River–style investment management platform.

A trader stages a bond order → it clears **pre-trade compliance** → it is **routed** to an
execution venue → **fills** stream back and update the firm's **positions** in real time.
Every state change is published to **Kafka**, where an independent **risk microservice**
consumes the stream to maintain a live view of desk exposure.

> Built with the exact stack a Fixed Income trading engineering team uses: **Java 21 +
> Spring Boot** APIs, **React + TypeScript** UI, **PostgreSQL**, **Kafka** event streaming,
> **Docker** & **Kubernetes**, with automated tests and CI.

---

## Architecture

```
                         ┌──────────────────────────┐
   Trader (browser)      │  React + TypeScript UI    │
   ───────────────────▶  │  order ticket · blotter · │
                         │  positions (Vite/nginx)   │
                         └───────────┬──────────────┘
                                     │ REST /api  (JSON)
                                     ▼
                         ┌──────────────────────────┐        ┌───────────────────┐
                         │   OMS Backend (Spring)    │        │  PostgreSQL        │
                         │  ┌─────────────────────┐  │  JPA   │  orders · security │
                         │  │ Order lifecycle FSM │  │◀──────▶│  execution · pos.  │
                         │  │ Compliance engine   │  │ Flyway └───────────────────┘
                         │  │ Position keeper     │  │
                         │  │ CLOB matching engine│  │
                         │  └─────────┬───────────┘  │
                         └────────────┼──────────────┘
                                      │ publishes OrderEvent
                                      ▼
                         ┌──────────────────────────┐
                         │        Kafka topic        │  order-events (keyed by orderRef)
                         │      "order-events"       │
                         └────────────┬──────────────┘
                                      │ consumes
                                      ▼
                         ┌──────────────────────────┐
                         │   Risk Service (Spring)   │  aggregates desk risk from the
                         │  @KafkaListener + REST     │  event stream (own microservice)
                         └──────────────────────────┘
```

**Why event-driven?** The OMS never calls the risk service directly — it only emits
events. New consumers (audit, P&L, market-data) can be added without touching the OMS.
Events are keyed by order reference so all events for one order stay strictly ordered on
the same partition, and the risk aggregator is **idempotent** (replaying the topic yields
the same numbers).

---

## How this maps to the role

| Job requirement | Where it lives in this project |
|---|---|
| **Java** backend APIs | `backend/` — Spring Boot 3.3, Java 21 |
| **JavaScript/TypeScript + React** UI | `frontend/` — React 18 + TypeScript + Vite |
| **API development (Spring Boot)** | REST controllers, DTO validation, OpenAPI/Swagger |
| **Relational databases (SQL)** | PostgreSQL, **Flyway** migrations, **hand-written analytical SQL** (joins, `GROUP BY`, CTEs, window functions) via `JdbcTemplate` for the reporting/TCA layer |
| **Fixed Income trading workflows** | Bond order lifecycle, pre-trade compliance, fills, positions, transaction cost analysis |
| **Kafka / event-driven / microservices** | `OrderEvent` → Kafka → separate `risk-service` consumer |
| **Docker & Kubernetes** | Multi-stage `Dockerfile`s, `docker-compose.yml`, `k8s/` manifests |
| **Test automation (unit/integration/UI)** | 105 backend (JUnit 5, Mockito, MockMvc, jqwik, **Testcontainers**/real Postgres) + 52 Python research + **Vitest/RTL** component tests + **Playwright** E2E |
| **Code review / clean code / TDD** | Layered design, small classes, CI on every push |
| **Data structures & algorithms** | **CLOB matching engine** (price-time priority, `TreeMap` levels + FIFO queues), state machine, weighted-average cost, streaming aggregation |
| **Numerical methods / quant** | **Yield-to-maturity solver (Newton–Raphson)**, duration, convexity, DV01, accrued interest |
| **Real-time data / WebSockets** | Live **Coinbase** order-book feed (JDK WebSocket) → depth ladder + **paper trading against real liquidity** with genuine slippage |
| **Quant research / Python** | `research/` — **Parquet + DuckDB** warehouse, hand-rolled econometrics (**cointegration, OU half-life**), cost-aware **backtester**, BTC/ETH **stat-arb** study with an honest (overfit-flagging) verdict |
| **Trading strategies / TCA** | `strategy/` — **execution algos** (TWAP/POV/**Almgren–Chriss**) with implementation-shortfall TCA, and an **Avellaneda–Stoikov market maker** — live on the feed |

---

## Domain model

- **Security** — bond reference data (CUSIP, ISIN, coupon, maturity, rating, sector,
  clean price, restricted flag). Seeded with 12 realistic bonds (Treasuries + corporates).
- **Order** — a bond order with quantity in **par notional** and prices as **% of par**
  (the market convention). Lifecycle: `NEW → STAGED → ROUTED → PARTIALLY_FILLED → FILLED`,
  or `CANCELLED` / `REJECTED`. Legal transitions are encoded on the `OrderStatus` enum.
- **Execution** — an individual fill (partial or full) reported by a venue.
- **Position** — the desk's signed holding per (portfolio, security), maintained
  incrementally with weighted-average cost — including the tricky **flip-through-zero** case.

### Pre-trade compliance (Strategy pattern)

Each rule is a Spring bean implementing `ComplianceRule`; the engine runs all of them and
aggregates breaches, so adding a rule means adding one class:

- **Restricted list** — blocks trading in flagged securities.
- **Minimum credit rating** — blocks *buys* below the desk floor (BB-).
- **Max order notional** — blocks oversized single orders (> $25MM).
- **Concentration limit** — blocks orders that would over-expose a portfolio to one name.

Beyond per-order compliance, an **aggregate pre-trade risk guard** (`PreTradeRiskGuard`) caps the
book's total gross notional across all open positions (`oms.risk.max-gross-notional`), so live
protection isn't limited to the backtester's kill-switches. A breach doesn't error out — the order
is persisted as `REJECTED` with the reason, mirroring a real desk's audit trail.

---

## Matching engine (the exchange core)

Routed orders are matched by a real **central limit order book** (`backend/.../matching/`),
not a random fill simulator. It implements strict **price-time priority**:

- Price levels in `TreeMap`s (best price O(1) to read, any level O(log n) to find); each
  level is a FIFO `ArrayDeque` for time priority. Cancels are lazy → O(1).
- Prices are **integer ticks** and quantities are `long`s, so the hot path does only
  integer arithmetic — no `BigDecimal`, no per-compare allocation.
- Handles limit/market orders, partial fills, price improvement to the aggressor, and
  cancel; the book is a **single-threaded core** (concurrency handled by a lock per book).
- An automated **market-maker** (`LiquidityProvider`) keeps a two-sided book in every
  security, so the desk always trades against genuine resting liquidity. Fills flow back
  to the OMS as Spring events, keeping the engine free of any persistence dependency.

**Correctness — property-based tests (jqwik).** Hundreds of randomized order flows assert
the invariants a real exchange depends on: the book is *never crossed*, *quantity is
conserved* across matches, *no order ever trades through its limit*, and resting quantity
always reconciles. (One of these caught a real modeling bug during development.)

**Performance — benchmark.** Single-threaded, no I/O
(`java -cp target/classes com.bonddesk.oms.matching.MatchingBenchmark`):

```
throughput   : ~3,300,000 orders/sec
latency p50  : ~150 ns      p99 : ~1.9 µs      p99.9 : ~9 µs (tail varies run-to-run)
```

Measured on an Intel Core i5-8279U (JDK 21); throughput and p50/p99 reproduce consistently,
the p99.9 tail is noisy. Re-run the harness above to reproduce on your own hardware.

> Design note: matching now happens under the per-book lock, but fills are collected and the
> `@Transactional` persistence runs *after* the lock is released, so the matching core never
> blocks on DB I/O while holding the book. A production HFT path would go further and hand fills
> to an append-only event queue; the benchmark above measures the pure in-memory core.

---

## Bond analytics (from first principles)

`backend/.../pricing/BondMath` computes fixed-income risk from discounted cash flows —
hand-rolled to show the numerical method, not a library call:

- **Yield to maturity** via **Newton–Raphson** (analytic derivative, not finite-difference)
- **Accrued interest** (30/360), clean vs. **dirty price**
- **Macaulay & modified duration**, **convexity**, and **DV01**

Exposed at `GET /api/securities/{cusip}/analytics`; covered by tests asserting
par/discount/premium yield relationships, accrued interest, and price round-tripping.

---

## Live market data — real Coinbase feed (capability showcase)

> This platform is **fixed-income-first** (above). This module is a self-contained
> demonstration that the order-book engine is **asset-agnostic** and can integrate a
> **real-time exchange feed** — not a change of focus. It lives in its own `market/`
> package and "Live Market" tab, gated by `oms.crypto.enabled`.

The same order-book machinery is asset-agnostic, so a **"Live Market" module** streams the
**real Coinbase order book** and lets the desk **paper-trade against genuine liquidity**:

- A **WebSocket client** (JDK built-in — no dependency) subscribes to Coinbase Advanced
  Trade's public `level2` (full depth) and `market_trades` channels — **no API key required**.
- `LiveOrderBook` reconstructs each product's book from the snapshot + incremental updates;
  a live **depth ladder**, **spread/quote**, and **trade tape** are exposed over REST.
- **Paper trading against the live book**: a market/limit order sweeps the real resting
  liquidity level-by-level, paying **genuine multi-level slippage** vs. the arrival mid
  (e.g. a 1.5 BTC market order filling across ~20+ real price levels), and updates a
  crypto position with **live mark-to-market**.

This grounds the platform in **real liquidity levels and price action** — the matching
mechanics (sweep best-first, partial fills, slippage) are identical whether the book is a
bond CLOB or a crypto exchange. Disabled by config (`oms.crypto.enabled`) in tests/offline.

---

## Quant research & backtesting (Python — `research/`)

On top of the live feed sits a **Python research layer** — mirroring how quant desks
actually split things: the Java/Spring system does low-latency trading; **Python does
research** over a columnar data warehouse. (Polyglot *for the right reason*.)

- **Data architecture**: raw capture is an append-only log; the analytical store is
  **columnar Parquet (zstd, partitioned) queried with DuckDB** — candles cached as Parquet
  so studies don't re-hit the API. (Not CSV-as-a-database.)
- **Hand-rolled econometrics** (no statsmodels): OLS, ADF unit-root, **Engle–Granger
  cointegration**, **Ornstein–Uhlenbeck half-life**.
- **Honest backtester**: transaction costs + a **one-period execution lag (no look-ahead)**,
  reporting Sharpe / drawdown / turnover / hit-rate.
- **BTC/ETH stat-arb study** that is built to *catch itself out*: it separates an in-sample
  cointegration **diagnostic** from a **walk-forward out-of-sample** backtest (β re-fit on a
  trailing window, traded on the next block). On real data the pair is **not cointegrated**, and
  the shiny in-sample Sharpe of **3.56 collapses to −0.62 out-of-sample** — the "edge" was the
  leakage. Reported as an honest negative result, not alpha. 52 tests on synthetic data. See
  [`research/README.md`](research/README.md).

---

## Strategy engine — execution algos + market making (live, with TCA)

A unified **strategy engine** (`backend/.../strategy/`) runs trading strategies against the
live Coinbase feed, covering **both sides of the market** with shared P&L / TCA plumbing:

- **Execution algorithms (taker)** — **TWAP**, **POV** (percentage-of-volume), and
  **Almgren–Chriss** optimal execution (risk-averse, front-loaded `sinh` trajectory). Each
  works a parent order down over time, sweeping the real book with a one-tick lag, and
  reports **implementation shortfall (bps) vs. the arrival mid** — the best-execution story.
- **Market making (maker)** — an **Avellaneda–Stoikov** market maker: quotes are centred on
  an **inventory-skewed reservation price** with an optimal spread, and get filled when a
  **real trade prints through them**. Tracks inventory, spread capture and live P&L — the
  sell-side story.
- **Shared core** — `PnlBook` (average-cost, realized/unrealized, flip-through-zero),
  `MarketState` (rolling volatility + recent volume), a 500 ms `StrategyRunner`, and a REST
  API + a **"Strategies" UI tab** to launch runs and watch P&L / inventory / quotes /
  shortfall live. 9 unit tests.

Verified live: a TWAP buy filled across 14 real book levels (**−0.38 bps** shortfall); the
Avellaneda–Stoikov maker took real fills on ETH and accrued inventory with live P&L.

---

## Running it

### Option A — Local dev (needs only a JDK 21 and Node 20)

```bash
# 1) OMS backend (in-memory H2, CLOB matching engine + market-maker on) → :8080
cd backend && ./mvnw spring-boot:run

# 2) Trader UI (Vite dev server, proxies /api to :8080) → :5173
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** — stage an order, click **Stage → Route**, and watch the
matching engine fill it against the market-maker's book and build your position. API docs at
**http://localhost:8080/swagger-ui.html**.

### Option B — Full stack with Docker Compose (Postgres + Kafka + risk service)

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Trader UI | http://localhost:8088 |
| OMS API / Swagger | http://localhost:8080/swagger-ui.html |
| Risk summary | http://localhost:8081/api/risk/summary |

### Option C — Kubernetes

```bash
# build & load images (e.g. into kind/minikube), then:
kubectl apply -f k8s/
kubectl -n bonddesk get pods
```

---

## API reference (OMS backend)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/securities` | List bonds (reference data) |
| `GET` | `/api/securities/{cusip}/analytics` | Bond analytics: YTM, accrued, duration, convexity, DV01 |
| `GET` | `/api/orders` | The blotter (filter by `?status=` or `?portfolio=`) |
| `POST` | `/api/orders` | Stage a new order (runs compliance) |
| `POST` | `/api/orders/{ref}/stage` | Release order (`NEW → STAGED`) |
| `POST` | `/api/orders/{ref}/route` | Route to venue (`STAGED → ROUTED`) |
| `POST` | `/api/orders/{ref}/fills` | Report a fill |
| `POST` | `/api/orders/{ref}/cancel` | Cancel a working order |
| `GET` | `/api/portfolios/{portfolio}/positions` | Positions with mark-to-market |
| `GET` | `/api/analytics/desk-summary` | Order counts, fill rate, filled notional (aggregate SQL) |
| `GET` | `/api/analytics/execution-quality` | TCA: avg fill vs. benchmark, slippage (bps) by security/side |
| `GET` | `/api/analytics/top-securities?limit=` | Highest-volume securities |
| `GET` | `/api/analytics/daily-volume` | Daily volume + running total (window function) |
| `GET` | `/api/market/products` | Live Coinbase quotes (best bid/ask, spread, last) |
| `GET` | `/api/market/{product}/book` | Live depth ladder (real order book) |
| `GET` | `/api/market/{product}/trades` | Real trade tape |
| `GET` | `/api/market/{product}/microstructure` | Rolling signals: imbalance, microprice premium, spread |
| `POST` | `/api/market/{product}/orders` | Paper-trade against the live book (VWAP + slippage) |
| `GET` | `/api/market/positions` | Crypto positions with live mark-to-market |
| `POST` | `/api/strategies` | Launch a strategy (TWAP/POV/Almgren–Chriss or Avellaneda–Stoikov) |
| `GET` | `/api/strategies` | Strategy runs with live P&L / inventory / TCA |
| `POST` | `/api/strategies/{id}/stop` | Stop a running strategy |
| `GET` | `/api/risk/summary` | *(risk-service :8081)* Desk risk aggregated from events |

---

## SQL & the reporting layer

The **transactional** side (orders, fills, positions) is persisted through JPA/Hibernate.
The **reporting** side is deliberately written in **hand-crafted SQL** via `JdbcTemplate`
(`AnalyticsService`) — a realistic split that keeps analytical queries explicit and tunable:

- **Joins + aggregation** across `orders`, `execution`, and `security` for transaction cost analysis
- **Conditional aggregation** (`CASE WHEN …`) for the one-pass desk summary / fill-rate
- **A CTE + window function** (`SUM(…) OVER (ORDER BY day)`) for daily volume with a running total
- **`GROUP BY … ORDER BY … LIMIT`** for top-volume securities
- **Flyway** owns schema evolution: `V1__schema.sql` (tables) and `V2__analytics.sql`
  (supporting indexes + a `v_execution_quality` reporting **view**)

All analytical SQL is written to run unchanged on **PostgreSQL** (prod) and **H2** in
PostgreSQL-compatibility mode (dev/test), and is covered by integration tests.

---

## Testing

```bash
cd backend      && ./mvnw test         # 105 tests (unit + integration; integration needs Docker)
cd risk-service && ./mvnw test         #  3 tests
cd frontend     && npm test            #  8 component tests (Vitest + RTL)
cd frontend     && npm run test:e2e    #  Playwright E2E (needs the stack running)
```

**Backend** — the **matching engine** (unit + jqwik property invariants), the order-status
**state machine**, the **weighted-average cost** logic, the **bond math** (YTM / duration /
convexity / accrued), the **compliance** rules, the full **HTTP layer** (MockMvc: validation
400s, compliance 201-REJECTED, lifecycle, 404/409/CORS), and **idempotent** risk aggregation.
Integration tests run against a **real PostgreSQL via Testcontainers** (exercising the actual
Flyway migrations + Hibernate `validate`), not H2 — pass `-Dtest.postgres.url=...` to target an
existing database instead.

**Frontend** — **Vitest + React Testing Library** component tests (order ticket validation +
compliance-reject banner, blotter rendering + lifecycle actions), plus a **Playwright** E2E
that drives stage → route → fill through the real UI and API. All wired into CI.

---

## Project structure

```
bonddesk-oms/
├── backend/            # Spring Boot OMS
│   └── src/main/java/com/bonddesk/oms/
│       ├── matching/   #   CLOB matching engine, market-maker, benchmark
│       ├── pricing/    #   bond math (YTM, duration, convexity, DV01)
│       ├── analytics/  #   raw-SQL reporting / TCA
│       ├── compliance/ #   pluggable pre-trade rules
│       └── ...         #   domain, services, controllers, events, Flyway
├── risk-service/       # Spring Boot Kafka consumer: desk-risk aggregation microservice
├── frontend/           # React + TypeScript trader UI (Vite)
├── k8s/                # Kubernetes manifests (namespace, pg, kafka, services, ingress)
├── docker-compose.yml  # One-command full stack
└── .github/workflows/  # CI: build + test all three services, build images
```

---

## Tech stack

**Backend:** Java 21 · Spring Boot 3.3 (Web, Data JPA, Validation, Actuator) · Spring Kafka ·
Hibernate · Flyway · PostgreSQL / H2 · springdoc-openapi · JUnit 5 · Mockito · AssertJ · Maven
**Frontend:** React 18 · TypeScript 5 · Vite 5
**Infra:** Docker (multi-stage) · Docker Compose · Kubernetes · GitHub Actions · nginx
