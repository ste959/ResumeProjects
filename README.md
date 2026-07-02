# BondDesk OMS — Fixed Income Order & Execution Management System

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
                         │  │ Execution simulator │  │
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
| **Relational databases (SQL)** | PostgreSQL + JPA/Hibernate + **Flyway** migrations |
| **Fixed Income trading workflows** | Bond order lifecycle, pre-trade compliance, fills, positions |
| **Kafka / event-driven / microservices** | `OrderEvent` → Kafka → separate `risk-service` consumer |
| **Docker & Kubernetes** | Multi-stage `Dockerfile`s, `docker-compose.yml`, `k8s/` manifests |
| **Test automation (unit/integration)** | 28 tests: JUnit 5, Mockito, MockMvc, AssertJ |
| **Code review / clean code / TDD** | Layered design, small classes, CI on every push |
| **Data structures & algorithms** | State-machine transitions, weighted-average cost, streaming aggregation |

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

A breach doesn't error out — the order is persisted as `REJECTED` with the reason, mirroring
a real desk's audit trail.

---

## Running it

### Option A — Local dev (needs only a JDK 21 and Node 20)

```bash
# 1) OMS backend (in-memory H2, background execution simulator on) → :8080
cd backend && ./mvnw spring-boot:run

# 2) Trader UI (Vite dev server, proxies /api to :8080) → :5173
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** — stage an order, click **Stage → Route**, and watch the
execution simulator fill it and build your position. API docs at
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
| `GET` | `/api/orders` | The blotter (filter by `?status=` or `?portfolio=`) |
| `POST` | `/api/orders` | Stage a new order (runs compliance) |
| `POST` | `/api/orders/{ref}/stage` | Release order (`NEW → STAGED`) |
| `POST` | `/api/orders/{ref}/route` | Route to venue (`STAGED → ROUTED`) |
| `POST` | `/api/orders/{ref}/fills` | Report a fill |
| `POST` | `/api/orders/{ref}/cancel` | Cancel a working order |
| `GET` | `/api/portfolios/{portfolio}/positions` | Positions with mark-to-market |
| `GET` | `/api/risk/summary` | *(risk-service :8081)* Desk risk aggregated from events |

---

## Testing

```bash
cd backend      && ./mvnw test    # 25 tests
cd risk-service && ./mvnw test    #  3 tests
cd frontend     && npm run build  # tsc typecheck + production build
```

Coverage includes: the order-status **state machine**, the **weighted-average cost** logic
(add / reduce / close / flip), the **compliance** rules (restricted, rating, notional),
the full **HTTP layer** (MockMvc: validation 400s, compliance 201-REJECTED, lifecycle,
404/409 handling), and **idempotent** risk aggregation over the event stream.

---

## Project structure

```
bonddesk-oms/
├── backend/            # Spring Boot OMS: domain, compliance, services, REST, Flyway
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
