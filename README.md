# Low-Latency Trading Platform

A polyglot **systems-engineering** project built around a hard problem domain. Trading is the vehicle;
the substance is software: a sub-microsecond matching engine, event-driven microservices with
effectively-once messaging, a from-scratch expression **compiler**, and a deterministic **validation
harness**. Java 21 · Python 3.12 · TypeScript. **630+ automated tests**, built AI-forward behind
committed guardrails.

[![CI](https://github.com/ste959/ResumeProjects/actions/workflows/ci.yml/badge.svg)](https://github.com/ste959/ResumeProjects/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ste959/ResumeProjects/actions/workflows/codeql.yml/badge.svg)](https://github.com/ste959/ResumeProjects/actions/workflows/codeql.yml)
![Java 21](https://img.shields.io/badge/Java-21-orange)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB)
![TypeScript 5](https://img.shields.io/badge/TypeScript-5-3178C6)
![Apache Kafka](https://img.shields.io/badge/Kafka-event--driven-231F20)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Flyway-336791)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![Kubernetes](https://img.shields.io/badge/Kubernetes-manifests-326CE5)
![tests](https://img.shields.io/badge/tests-630%2B%20passing-brightgreen)
![matching engine](https://img.shields.io/badge/matching%20engine-~3M%20ord%2Fs%20%C2%B7%20p50%20~300ns-blueviolet)

📋 **Every claim here is checkable.** [**EVIDENCE.md**](EVIDENCE.md) maps each one to a test you can run, a
committed result, or an ADR — with what runs locally vs. in CI. Deep dive:
[**how effectively-once works**](docs/writeups/effectively-once.md).

Why trading? Because it forces the problems worth engineering: **low latency** (a match must clear in
nanoseconds), **correctness invariants** (an order book must never violate price-time priority),
**distributed consistency** (a fill in one service must reach another without loss or duplication), and
**large-data research** (thousands of signals over decades of history). Each subsystem below is a real
answer to one of those.

> **Not a finance person?** You don't need to be. Every domain term maps to a familiar software concept
> — an *order book* is a priority queue, *matching* is a merge, an *alpha signal* is a pure function over
> a time-series. The 3-minute **[finance-for-engineers primer](docs/domain-primer.md)** translates it all
> (and the UI glosses jargon inline on hover).

## Engineering highlights

| | What it is | The hard part | Evidence |
|---|---|---|---|
| **Matching engine** | A price-time-priority central limit order book (`com.bonddesk.exchange`) | O(1) cached top-of-book, O(log n) level lookup, O(1) cancel, allocation-free hot path (integer ticks/lots) | **~3M ord/s** single-thread (JMH, `-prof gc` = 193 B/order); a concurrent **load test** ([committed run](docs/benchmarks/matching-loadtest.txt), `make loadtest`) scales to ~4 threads then saturates on lock contention, p50 ~300 ns |
| **Event-driven microservices** | An OMS publishes `OrderEvent`s to Kafka; an independent risk service consumes them | The dual-write problem, solved with a **transactional outbox**; idempotent producer + idempotent consumer = **effectively-once** ([writeup](docs/writeups/effectively-once.md)); poison rows dead-lettered | `oms.event`, `risk-service/`; **Avro + Schema Registry** with a CI **schema-compatibility test** that fails the build on a backward-incompatible change ([ADR-0009](docs/adr/0009-schema-registry-avro.md)) |
| **A compiler** | An alpha-signal DSL — `rank(ts_delta(close,5)) - 0.5*zscore(volume)` | Lexer → **Pratt parser** → semantic checker → evaluator lowering to vectorized NumPy; the AST fingerprint drives a content-addressed cache and a parallel executor | `research/mds/alphadsl`, a **differential test** pinning the evaluator to the reference to 1e-12 |
| **Validation harness** | A dependency-free "readiness lab" for validating systems under test | Deterministic runner, pluggable adapters, telemetry (NDJSON/JUnit), a flakiness gate, repro bundles, hardware-aware regression gates, tamper-evident hash-chained results | `harness/` — 81 tests, pure standard library |
| **Full stack + platform** | React/TS front end, REST + WebSocket, PostgreSQL/Flyway, Docker/K8s, Prometheus/Grafana | Real persistence tested against **real Postgres** (Testcontainers), not H2 stand-ins; graceful shutdown; connection-pool + index tuning | `frontend/`, `backend/`, `docker-compose.yml`, `k8s/` |

## Architecture

```
                          React + TypeScript (Vite / nginx)
   Browser ───────────▶   Landing hub → /exchange · /oms · /research
                                │ REST + WebSocket
             ┌──────────────────┴───────────────────┐
             ▼                                       ▼
   ┌───────────────────────────────┐     ┌──────────────────────────┐
   │  OMS Backend (Spring, :8080)  │     │  Quant service (FastAPI,  │
   │  matching engine · rates desk │     │  :8082) research → back-  │
   │  cash OMS · market data · TCA │     │  test → live paper        │
   └───┬───────────────────┬───────┘     └──────────────────────────┘
  JPA/ │                   │ publishes OrderEvent (transactional outbox)
Flyway ▼                   ▼
 ┌──────────┐      ┌───────────────┐   @KafkaListener   ┌──────────────────┐
 │ Postgres │      │ Kafka         │ ─────────────────▶ │ Risk service      │
 │          │      │ order-events  │  (idempotent,      │ (Spring, :8081)   │
 └──────────┘      └───────────────┘   DLT on poison)   └──────────────────┘

 Observability: Prometheus + Grafana · correlation-id logging · OpenAPI
```

The services are genuinely independent (each owns its schema/topic view and deploys on its own); they
share only the **JSON event contract** on the topic — enforced by the contract test — which is what
keeps them decoupled. See [ADR-0001](docs/adr/0001-transactional-outbox.md) for why the outbox, and
[ADR-0002](docs/adr/0002-two-matching-engines.md) for why there are two order books.

## Repository map

| Path | Stack | What lives there | Docs |
|---|---|---|---|
| [`backend/`](backend/) | Java 21, Spring Boot | Matching engine, OMS, rates desk, the Kafka outbox | [README](backend/README.md) |
| [`risk-service/`](risk-service/) | Java 21, Kafka | Event-driven risk aggregation + dead-letter handling | [README](risk-service/README.md) |
| [`frontend/`](frontend/) | React 18, TypeScript, Vite | Live book / market / desk views over REST + WebSocket | [README](frontend/README.md) |
| [`research/`](research/) | Python 3.12, pandas | Walk-forward engine + the **alpha-DSL compiler**, cache, parallel runner | [README](research/mds/alphadsl/README.md) |
| [`harness/`](harness/) | Python (stdlib) | The deterministic **validation harness** | [README](harness/README.md) |
| [`docs/`](docs/), [`.claude/`](.claude/), `CLAUDE.md` | — | ADRs, the AI-forward account, agent standards | [ENGINEERING.md](ENGINEERING.md) |

## Quality & CI

Claims in this repo are backed by tests, not prose — every number is reproducible from a command.

- **~600 automated tests** — Java 189 (incl. **jqwik property-based** invariants on the order book +
  **Testcontainers** integration tests against real Postgres), Python research 323, harness 81, frontend 8.
- **The strong kinds, on purpose:** *property-based* (invariants across generated inputs), *differential*
  (a new implementation must equal the reference it replaces, to 1e-12), *determinism / no-look-ahead*
  (seeded; reproducible), and a *consumer-driven contract test* across the service boundary.
- **CI** runs the whole matrix on every push — all services, the frontend, the validation harness (tests
  + flakiness gate + a tamper-evidence self-check), plus **CodeQL** SAST, **Trivy** image scanning, and
  **Dependabot**.
- Determinism is a rule, not a hope: seeded randomness only, no wall-clock or look-ahead in analysis/test
  paths.

## AI-forward, with guardrails

Built with heavy AI assistance — and the apparatus around it is committed and enforced, which is the
point. Agent operating standards live in [`CLAUDE.md`](CLAUDE.md), review subagents in
[`.claude/agents/`](.claude/agents/), and the honest account of how AI was used (and the deterministic
gates every AI change must pass, plus `Co-Authored-By` provenance) is in
[`docs/ai-assisted-engineering.md`](docs/ai-assisted-engineering.md). The bar: *AI accelerates;
reproducible tests, reviewed code, and accountable human judgment decide what ships.*

## Run it

```bash
make demo            # build + start the whole stack, then show data flowing across the services
make test            # every test suite (backend, risk, frontend, research, harness)
make loadtest        # matching-path throughput + tail latency under concurrent load
make harness         # run the validation lab (sealed, with repro bundles)
make help            # all targets
```

Per component:

```bash
cd backend   && ./mvnw -B verify          # matching engine + OMS (Docker for integration tests)
cd research  && python -m pytest -q        # quant engine + alpha DSL (323 tests)
python -m pytest harness -q                # validation harness (81 tests)
```

## Deeper reading

- **[ENGINEERING.md](ENGINEERING.md)** — the whole-platform engineering narrative (5-minute tour).
- **[docs/adr/](docs/adr/)** — architecture decision records (why the outbox, the two engines, integer
  ticks, the DSL, the harness).
- **[docs/follow-ups.md](docs/follow-ups.md)** — improvements deliberately deferred, with reasoning.
