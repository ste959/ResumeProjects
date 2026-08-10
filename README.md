# Quantitative Trading Platform

> Three independent trading applications behind a single landing hub — a **crypto matching
> engine + market maker**, a **fixed-income rates / dealer desk**, and a **research→backtest→live
> quant desk** — sharing one event-driven Java + Python + React stack.

[![CI](https://github.com/ste959/FixedIncomeTradingPlatform/actions/workflows/ci.yml/badge.svg)](https://github.com/ste959/FixedIncomeTradingPlatform/actions/workflows/ci.yml)
![Java 21](https://img.shields.io/badge/Java-21-orange)
![Spring Boot 3.3](https://img.shields.io/badge/Spring%20Boot-3.3-6DB33F)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)
![React 18](https://img.shields.io/badge/React-18-61DAFB)
![TypeScript 5](https://img.shields.io/badge/TypeScript-5-3178C6)
![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-event--driven-231F20)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![Kubernetes](https://img.shields.io/badge/Kubernetes-manifests-326CE5)
![Observability](https://img.shields.io/badge/observability-Prometheus%20%2B%20Grafana-E6522C)
![Tests](https://img.shields.io/badge/tests-320%2B%20passing-brightgreen)
![Matching engine](https://img.shields.io/badge/matching%20engine-~2.1M%20ord%2Fs-blueviolet)

A single **landing hub** (`/`) links three **self-contained, independently-navigable apps**, each its
own product with its own identity — not one mashed dashboard:

| App | Route | What it is |
|---|---|---|
| **Exchange & Market Maker** | `/exchange` | A price-time-priority **matching engine** anchored to a live Coinbase mid, with an Avellaneda–Stoikov **market maker** and maker P&L analytics. |
| **Fixed-Income Desk** | `/oms` | A **rates dealing desk** (multi-dealer RFQ + curve + key-rate risk), an electronic **cash OMS** (order lifecycle, compliance, positions), and a **risk & tax** layer. |
| **Quant Desk** | `/research` | An **Alpaca-backed research → backtest → live** pipeline: explore the market, walk-forward-validate a signal, then promote it to a live paper-trading strategy. |

They share a backbone — **Java 21 + Spring Boot** services, a **Python + FastAPI** quant service, a
**React + TypeScript** front end, **Kafka** event streaming, **PostgreSQL**, and **Docker / Kubernetes**.

> **📈 60-second visual overview:** open **[`research/showcase.html`](research/showcase.html)** in a browser
> (self-contained, no build) — the platform pipeline, all 11 honestly-tested strategies with their verdicts,
> and the flagship results, at a glance.

> **Where the depth is.** The **Quant Desk** is the finance flagship — a full **research-to-execution
> quant platform** with a Strategy SDK, a shared walk-forward engine, and an overfitting-aware validation
> gauntlet that takes a strategy from *concept → backtest → validation → risk → execution → attribution*.
> See **[`research/PLATFORM.md`](research/PLATFORM.md)**. The Exchange and Fixed-Income desks are
> **systems/SWE** showcases (matching-engine throughput, event-driven architecture); the exchange's
> order-book work also feeds the platform's execution-realism layer.

---

## Architecture

```
                             ┌───────────────────────── React + TypeScript (Vite / nginx) ─────────────────────────┐
   Browser  ───────────────▶ │   Landing hub  →  /exchange  ·  /oms  ·  /research                                   │
                             └───────┬───────────────────────┬───────────────────────────┬──────────────────────────┘
                                     │ REST + WebSocket        │ REST + WebSocket           │ REST  (/research-api)
                                     ▼                         ▼                            ▼
                       ┌───────────────────────────────────────────────────┐   ┌──────────────────────────────────┐
                       │        OMS Backend  (Spring Boot, :8080)          │   │  Quant Desk service (FastAPI,:8082)│
                       │  exchange (CLOB + maker) · rates (curve/RFQ/DV01) │   │  Alpaca client · live strategy     │
                       │  cash OMS (lifecycle · compliance · positions)    │   │  engine · walk-forward lab · risk  │
                       │  matching · market data · strategy · TCA          │   │  (vol-target + portfolio netting)  │
                       └───────┬───────────────────────────┬───────────────┘   └──────────────┬───────────────────┘
                    JPA/Flyway │                            │ publishes OrderEvent              │ REST
                               ▼                            ▼                                   ▼
                       ┌──────────────┐            ┌──────────────────┐                 ┌──────────────────┐
                       │  PostgreSQL  │            │  Kafka  "order-  │  @KafkaListener │  Alpaca paper +   │
                       │              │            │      events"     │ ───────────────▶│  market data API  │
                       └──────────────┘            └────────┬─────────┘                 └──────────────────┘
                                                            ▼
                                                 ┌────────────────────┐
                                                 │  Risk Service      │  aggregates desk risk from the
                                                 │  (Spring, :8081)   │  event stream (own microservice)
                                                 └────────────────────┘
```

**Why event-driven?** The OMS never calls the risk service directly — it only emits `OrderEvent`s to
Kafka, keyed by order reference so all events for one order stay ordered on one partition. New
consumers (risk, audit, P&L) attach without touching the OMS, and the risk aggregator is **idempotent**
(replaying the topic yields the same numbers).

---

## 1 · Exchange & Market Maker  (`/exchange`)

A real **central limit order book (CLOB)** with strict **price-time priority** (`com.bonddesk.exchange`),
anchored to a **live Coinbase BTC mid** so the simulation tracks real price action.

- **Order types:** LIMIT / MARKET / IOC / FOK / post-only, cancel-replace, self-trade prevention, L2/L3
  market data. Price levels in `TreeMap`s (best O(1) to read), each a FIFO queue for time priority;
  integer ticks + `long` quantities keep the hot path allocation-free.
- **Market making:** an **Avellaneda–Stoikov** maker quotes around an inventory-skewed reservation
  price; an agent-based flow generator supplies noise makers, informed takers, and noise traders.
- **Analytics** decompose maker P&L into **spread capture vs. adverse selection vs. inventory**, with
  per-fill **markouts**, a sortable fill log, and **latency-by-match-depth** buckets.

**Benchmark** (single-threaded, in-memory; `com.bonddesk.exchange.*`, reproduce with
`./mvnw test -Dtest=ExchangeBenchmarkTest`):

```
throughput   : ~2,160,000 orders/sec
latency p50  : ~300 ns     p99 : ~2.2 µs     p99.9 : ~17 µs   (tail varies run-to-run)
```

*Measured on a laptop-class CPU under JDK 21; throughput and p50 reproduce consistently, the p99.9 tail
is noisy. This is the pure in-memory core, not a networked exchange.*

---

## 2 · Fixed-Income Desk  (`/oms`)

An electronic **order & execution management system** for bonds, plus a live **rates dealing desk** —
the workflows a Charles River-style investment-management platform runs.

- **Rates dealing (`com.bonddesk.rates`):** bootstraps a **discount curve from par yields**; prices
  bonds off a **z-spread** (bisection); computes **DV01, bucketed key-rate DV01** (localizes risk and
  sums to parallel DV01), **spread DV01, convexity, and modified/Macaulay duration**. A live **multi-dealer
  RFQ market** — dealers quote with inventory skew and competitive shading, a **best-execution auction**
  fills client RFQs, and **information leakage is modeled as λ·size·ln(1+n_dealers)**. Driven off a real
  Treasury curve, re-bootstrapped each tick, with **P&L attribution into carry / curve-parallel /
  reshaping / credit** + TCA.
- **Cash OMS:** bond order lifecycle (`NEW → STAGED → ROUTED → PARTIALLY_FILLED → FILLED` / `CANCELLED`
  / `REJECTED`) with a legal-transition state machine; **pluggable pre-trade compliance** (restricted
  list, min credit rating, max notional, concentration) plus an aggregate gross-notional risk guard;
  positions maintained with weighted-average cost (incl. the **flip-through-zero** case).
- **Bond analytics from first principles:** YTM via **Newton–Raphson**, accrued interest (30/360),
  clean vs. dirty price, duration / convexity / DV01 — hand-rolled to show the numerical method.
- **Reporting / TCA in hand-written SQL** (`JdbcTemplate`): joins + conditional aggregation for the
  desk summary, a CTE + window function for running daily volume, `v_execution_quality` view for
  slippage-vs-benchmark. Transactional side is JPA/Hibernate; **Flyway** owns schema evolution.

---

## 3 · Quant Desk  (`/research`)

An end-to-end **research → backtest → live** pipeline, backed by a real **Alpaca paper account**, served
by the Python **FastAPI** quant service (`research/service`). Three tabs, one honest workflow:

- **Exploration** — a live screener (most-active / movers), **server-computed technicals** (Wilder
  RSI-14, ATR-14, SMAs, returns), a **sector-ETF rotation** heatmap, the live news feed, and a
  **catalyst rail** (FOMC schedule + market calendar) — all off one Alpaca backbone.
- **Backtest** — a causal, cost-aware backtester with an **anchored walk-forward out-of-sample**
  validation and a real overfitting gauntlet: **Newey–West HAC t-stat, block-bootstrap Sharpe CI,
  Bonferroni multiple-testing correction, and a min-detectable-Sharpe power check**. Promotion to live
  is **gated server-side on out-of-sample survival** — the tool *rejects* strategies whose in-sample
  edge vanishes OOS.
- **Live Strategies** — a background engine trading the paper account, with **per-strategy P&L
  attribution reconstructed from tagged broker order history** and an automated risk layer:
  **volatility-targeted sizing** (risk budget ÷ asset vol), a **correlation-aware portfolio-vol cap**
  (√wᵀΣw, which nets correlated sleeves the gross cap can't), **per-sleeve loss stops**, and a
  **latching drawdown auto-flatten** kill switch. Disarmed by default; opt-in token auth on order control.

Underneath sits a deeper **Python research layer** (`research/mds`): a leakage-free cross-sectional
**factor pipeline** with purge/embargo CV, **Deflated Sharpe & PBO**, a **factor risk-model optimizer**
(Σ = BFBᵀ + D, constrained MVO), regime timing, options structuring, tax-aware rebalancing, and a
**multi-asset strategic/tactical asset-allocation** study (risk parity, min-variance, momentum-tilted
TAA vs. 60/40), and an **enhanced trend-following** book built up by *ablation* (multi-timescale signal,
vol-targeting + a correlation-aware portfolio-vol overlay, a carry blend, crash-protection) — all
walk-forward on real ETF data, **excess of cash**, with tail-risk metrics, **regime** robustness, and a
parameter **sensitivity** sweep, judged by one shared overfitting-aware gauntlet. See
[`research/README.md`](research/README.md) and the write-ups in [`RESEARCH-NOTE.md`](research/RESEARCH-NOTE.md),
[`ASSET-ALLOCATION-NOTE.md`](research/ASSET-ALLOCATION-NOTE.md), [`TREND-NOTE.md`](research/TREND-NOTE.md),
[`SIGNAL-RATIONALE.md`](research/SIGNAL-RATIONALE.md), and [`DECISIONS.md`](research/DECISIONS.md) (research
integrity log).

> **Honest by design.** The live strategies are simple (MA-crossover / momentum) *machinery
> demonstrations*, not alpha — and the walk-forward correctly refuses them on real crypto because taker
> fees eat the edge. The achievement is the pipeline that won't let you deploy an overfit strategy.

---

## Running it

### Full stack — Docker Compose

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Landing hub / all three apps | http://localhost:8088 |
| OMS API / Swagger | http://localhost:8080/swagger-ui.html |
| Risk summary (risk-service) | http://localhost:8081/api/risk/summary |
| Quant Desk API (research-service) | http://localhost:8082/api/research/health |
| Prometheus | http://localhost:9090 |
| Grafana (admin / admin) | http://localhost:3000 |

The **Quant Desk's Live tab is optional** and self-gates: with no Alpaca keys it shows a "connect
Alpaca" state; supply paper-trading keys to light it up (see below). The Exchange (Coinbase) and
Fixed-Income (US Treasury curve) feeds are **keyless**.

**Alpaca keys (optional, for the Quant Desk live/market features):** copy `.env.example` → `.env` at the
repo root and fill in a free **Alpaca paper** key/secret. `.env` and `alpaca-local.yml` are gitignored
and never committed.

### Kubernetes

```bash
kubectl apply -f k8s/          # namespace, postgres, kafka, backend, risk-service, frontend
kubectl -n bonddesk get pods
```

---

## Monitoring & observability

Every service is instrumented for production-style monitoring, and the compose stack ships a
**Prometheus + Grafana** pair that scrapes and visualizes them out of the box.

- **Health** — Spring Boot Actuator `/actuator/health` with **custom component indicators**: a
  `matchingEngine` check (UP only when the book is live and accepting orders — reports accepted
  orders, trades, throughput) and a `marketDataFeed` check (UP while the Coinbase feed is fresh,
  DOWN if it goes stale) alongside the built-in db / disk / ping checks.
- **Metrics** — Micrometer exposes `/actuator/prometheus` (JVM, HTTP latency/throughput) plus
  **custom domain metrics** from the matching engine: `exchange_orders_accepted_total`,
  `exchange_trades_total`, `exchange_throughput_orders_per_second`, and `exchange_latency_p50/p99_nanos`.
  The Python Quant Desk exposes `/metrics` too, so all services land on one dashboard.
- **Tracing** — a `CorrelationIdFilter` tags every request (from `X-Correlation-ID` or a fresh UUID),
  puts it in the SLF4J MDC so **every log line for a request carries the id**, and echoes it back on
  the response — the basis for request tracing across services.
- **Dashboards** — Grafana auto-provisions the Prometheus datasource and a **"BondDesk — Platform
  Overview"** dashboard (engine throughput, match latency, trades/sec, JVM heap, HTTP request rate)
  on first boot. Open http://localhost:3000 (admin / admin).

```bash
curl localhost:8080/actuator/health      # component-level UP/DOWN with details
curl localhost:8080/actuator/prometheus  # scrape target (custom + JVM/HTTP metrics)
```

---

## Testing

```bash
cd backend      && ./mvnw test        # 165 tests — matching engine (jqwik property invariants),
                                      #   rates engine, dealer market, bond math, compliance, state
                                      #   machine, HTTP layer (MockMvc), idempotent risk aggregation;
                                      #   integration tests use real PostgreSQL via Testcontainers
cd risk-service && ./mvnw test        # Kafka-consumer risk aggregation
cd research     && python -m pytest   # 155 tests — walk-forward lab, live-engine fake-broker harness
                                      #   (arm/kill/flatten/drawdown), risk math, microstructure, factors
cd frontend     && npm test           # Vitest + RTL component tests
cd frontend     && npm run test:e2e   # Playwright E2E (needs the stack running)
```

**300+ automated tests** across the stack. The live-engine tests drive the money path through a
**fake broker** (order submission, kill switch, per-sleeve stops, drawdown auto-flatten) with no live
API; the backend integration tests run against a **real PostgreSQL via Testcontainers**.

---

## How this maps to a Fixed-Income engineering role

| Requirement | Where it lives |
|---|---|
| **Fixed-income trading workflows** | Rates dealing desk (RFQ, curve, DV01/key-rate risk), bond order lifecycle, compliance, positions, TCA |
| **Java** backend APIs | `backend/` — Spring Boot 3.3, Java 21; REST + WebSocket |
| **JavaScript/TypeScript + React** | `frontend/` — React 18 + TS 5 + Vite, three routed apps |
| **Relational databases (SQL)** | PostgreSQL, **Flyway** migrations, hand-written analytical SQL (joins, `GROUP BY`, CTEs, window functions) via `JdbcTemplate` |
| **Kafka / event-driven / microservices** | `OrderEvent` → Kafka → independent `risk-service` consumer; a separate Python quant service |
| **Docker & Kubernetes** | Multi-stage `Dockerfile`s, `docker-compose.yml`, `k8s/` manifests |
| **Test automation / TDD / code review** | 300+ tests (JUnit 5, Mockito, MockMvc, jqwik, Testcontainers, pytest, Vitest, Playwright); CI on every push |
| **Data structures & algorithms** | CLOB order book (`TreeMap` levels + FIFO queues), state machine, weighted-average cost, streaming aggregation |
| **Numerical methods** | Newton–Raphson YTM, curve bootstrap, DV01/key-rate/convexity, covariance/portfolio-vol math |

---

## Project structure

```
├── backend/              # Spring Boot (:8080)
│   └── src/main/java/com/bonddesk/
│       ├── exchange/     #   standalone CLOB matching engine + market maker
│       ├── rates/        #   curve bootstrap, bond math, dealer/RFQ market
│       └── oms/          #   cash OMS: lifecycle, compliance, matching, market data,
│                         #   strategy, analytics/TCA, tax, wiring for exchange + rates
├── risk-service/         # Spring Boot Kafka consumer — desk-risk aggregation (:8081)
├── research/             # Python quant layer
│   ├── service/          #   FastAPI Quant Desk — Alpaca client, live engine, walk-forward lab, risk (:8082)
│   ├── mds/              #   research modules — factors, risk model, microstructure, validation
│   └── tests/            #   155 pytest tests
├── frontend/             # React + TypeScript — landing hub + three apps (:8088 via nginx)
├── k8s/                  # Kubernetes manifests
├── docker-compose.yml    # One-command full stack
└── .github/workflows/    # CI: build + test all services
```

---

## Tech stack

**Backend:** Java 21 · Spring Boot 3.3 (Web, Data JPA, Validation, Kafka, Actuator) · Hibernate · Flyway ·
PostgreSQL / H2 · springdoc-openapi · JUnit 5 · Mockito · jqwik · Testcontainers · Maven
**Quant service:** Python 3.12 · FastAPI · NumPy · pandas · pytest
**Frontend:** React 18 · TypeScript 5 · Vite · Vitest / RTL · Playwright
**Observability:** Spring Boot Actuator · Micrometer · Prometheus · Grafana
**Infra:** Docker (multi-stage) · Docker Compose · Kubernetes · Apache Kafka · GitHub Actions · nginx

---

*Scope & honesty: the matching-engine throughput is an in-memory single-threaded microbenchmark; the
order flow and dealer market are agent-based simulations anchored to real prices; the Quant Desk trades
a paper account and its bundled strategies are machinery demonstrations, not validated alpha. Each is
labeled as such in the code and docs.*
