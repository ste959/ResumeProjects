# Evidence

Every headline claim in this project maps to something you can check without taking it on faith: a test
you can run, a committed result artifact, or an Architecture Decision Record that explains the *why*. This
page is the index. Where a check needs Docker (real Postgres / Kafka), that's labeled — those run in
**CI** on every push; everything else runs on a bare JDK / Node / Python.

**CI is green on every push** — the badges at the top of the [README](README.md) link straight to the
GitHub Actions runs (build + all suites, plus CodeQL SAST and Trivy image scanning).

## Tests — 630+ across five suites

| Suite | Count | Run it | Notes |
|---|---:|---|---|
| Backend (OMS) | 214 run (234 `@Test` + 4 `@Property` incl. integration) | `cd backend && ./mvnw -B verify` | Unit + web-layer + **Testcontainers integration** (needs Docker; the extra ~20 run in CI) |
| Risk service | 7 | `cd risk-service && ./mvnw -B verify` | Includes the Avro consumer-contract test |
| Frontend | 12 | `cd frontend && npm ci && npm test` | Vitest (auth, order ticket, blotter, status) |
| Research (Python) | 322 | `cd research && python -m pytest -q` | Includes the DSL **differential** test (evaluator vs reference, 1e-12) |
| Validation harness | 81 | `python -m pytest harness -q` | Pure standard library; determinism gate |

Run everything with `make test`. Nothing merges unless these gates pass.

## Claims → proof

| Claim | Proof (run / read) | Type |
|---|---|---|
| **Effectively-once** across the Kafka boundary (no lost/phantom/duplicate events) | **Writeup:** [docs/writeups/effectively-once.md](docs/writeups/effectively-once.md) · **ADR:** [0001](docs/adr/0001-transactional-outbox.md) · code: `oms.event.OutboxRelay` | writeup + ADR + code |
| **Schema compatibility is enforced** — a backward-incompatible change fails the build | `cd backend && ./mvnw -B -Dtest=OrderEventSchemaCompatibilityTest test` · **ADR:** [0009](docs/adr/0009-schema-registry-avro.md) | local test |
| Order events are **Avro over a Schema Registry**, round-tripped end to end | `OrderEventAvroSerdeTest` (uses an in-memory `mock://` registry — no broker needed) | local test |
| **Idempotent order creation** — a retried POST can't double-submit | `OrderIdempotencyTest`, `InMemoryIdempotencyStoreTest` | local test |
| **RBAC** — reads public, writes need a role; a denied write is 403 (not a masked 500) | `OrderControllerSecurityTest`, `JwtServiceTest` · code: `config.SecurityConfig` | local test |
| **Keyset pagination** — correct order, no gaps/overlaps, stable tie-break | `OrderRepositoryKeysetTest` (real DB via `@DataJpaTest`), `CursorTest` | local test |
| **Matching-path performance** — p50 ~300 ns; ~1.9M/s single-thread scaling to ~4.9M/s then lock-saturating | Committed run: [docs/benchmarks/matching-loadtest.txt](docs/benchmarks/matching-loadtest.txt) · reproduce: `make loadtest` | committed artifact |
| **Matching hot path (isolated)** — ~8M ops/s single-thread (a *separate*, tighter measurement) | committed run: [docs/benchmarks/matching-jmh.txt](docs/benchmarks/matching-jmh.txt) · reproduce: `make bench` (JMH) | committed artifact |
| **DSL evaluator matches the reference** to 1e-12 | the differential test in `research/mds/alphadsl` (in the research suite) | local test |
| **Resilience** — transient venue failures retry & trip a circuit breaker; terminal 4xx don't | `AlpacaBrokerClientResilienceTest` (local HTTP server) · **ADR:** [0008](docs/adr/0008-tracing-and-venue-resilience.md) | local test |
| **SLO burn-rate alerts** fire on a sustained error spike, quiet on healthy traffic | `make slo-rules` (`promtool test rules`) · policy: [docs/slo.md](docs/slo.md) | rule unit test |
| **Distributed tracing** across HTTP + Kafka (one trace per order) | **ADR:** [0008](docs/adr/0008-tracing-and-venue-resilience.md); enabled in both services' config | ADR + config |
| **Real persistence** (Postgres, not H2 stand-ins) | Testcontainers `*IntegrationTest` (Docker; runs in CI) | CI test |

## Design decisions (the *why*)

The [Architecture Decision Records](docs/adr/) record the non-obvious calls with their trade-offs and the
alternatives rejected — outbox vs dual-write (0001), two matching-engine implementations (0002), integer
ticks on the hot path (0003), the alpha DSL (0004), the validation harness (0005), tamper-evident seals
(0006), AI-forward guardrails (0007), tracing + resilience (0008), and the schema registry (0009).
