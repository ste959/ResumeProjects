# Engineering Overview

A polyglot platform (Java · Python · TypeScript) whose center of gravity is **software engineering**: a
low-latency matching engine, event-driven microservices, a compiler, and a deterministic validation
harness — built AI-forward, inside a guardrail apparatus, with ~570 automated tests behind it.

This document is the 5-minute tour. Depth lives in each area's own README; the honest account of *how*
it was built is in [`docs/ai-assisted-engineering.md`](docs/ai-assisted-engineering.md).

## Map

| Area | Path | Stack | What it is |
|---|---|---|---|
| Matching engine + OMS | `backend/` | Java 21, Spring Boot | Price-time-priority CLOB, rates desk, cash OMS, Kafka producer + transactional outbox |
| Risk service | `risk-service/` | Java 21, Kafka | Event-driven risk aggregation with dead-letter handling |
| Trader UI | `frontend/` | React 18, TypeScript | Live book/market/strategy views over REST + WebSocket |
| Quant research + **alpha DSL** | `research/` | Python 3.12 | Walk-forward engine, a signal-DSL compiler, a content-addressed cache, a parallel runner |
| **Validation harness** | `harness/` | Python (stdlib) | A deterministic "readiness lab" — the QRT-shaped work |
| AI governance | `CLAUDE.md`, `.claude/`, `docs/` | — | Agent standards, review subagents, transparency |

~44k lines of code. CI (`.github/workflows/`) runs every component plus CodeQL and Trivy on push/PR.

## The engineering, in three arcs

### 1 · A low-latency core, hardened under a senior-SWE audit

The crown jewel is the [`exchange`](backend/src/main/java/com/bonddesk/exchange/OrderBook.java) matching
engine: a price-time-priority order book on `TreeMap` price levels + FIFO queues + a hash index —
**O(log n) level lookup, O(1) cancel, O(1) cached top-of-book**, an allocation-free passive path
(integer ticks/lots). A **JMH** benchmark (forked JVM, `Blackhole`, `-prof gc`) reports **~3M orders/sec
single-thread and 193 B/order**, cross-validated by an in-test `ThreadMXBean` measurement.

A self-directed senior-SWE audit drove concrete fixes: a **FOK×self-trade-prevention invariant bug**, a
**transactional outbox** replacing a dual-write to Kafka, a **dead-letter consumer**, config-gated
**API-key auth**, and an honest benchmark rewrite. See [`README.md`](README.md).

### 2 · A compiler for alpha signals (`research/mds/alphadsl`)

Signals became a small language instead of hand-written code: **lex → Pratt parse → semantic-check →
lower to vectorized pandas**. A **differential test** pins the evaluator to the reference implementation
(`zscore(clip(zscore(x),-3,3))` == `factors.standardize(x)` to 1e-12). On top of the fingerprinted AST:
a **content-addressed cache** (precise, automatic invalidation; cross-process) and a **parallel research
runner** (forkserver pool, fault-isolated, shared cache). One coherent system —
*parsed → cached → executed in parallel*. See [`research/mds/alphadsl/README.md`](research/mds/alphadsl/README.md).

### 3 · A deterministic validation harness (`harness/`) — the readiness lab

The most QRT-relevant work: a dependency-free framework that validates a system under test the way a
hardware readiness lab does. Five layers, ~2.2k LOC, 69 tests, all pure standard library:

| Layer | Capability |
|---|---|
| **Foundation** | packaged scenario collateral · pluggable **adapters** (in-process + external subprocess with a `LAB_RESULT` contract) · deterministic runner · **NDJSON + JUnit XML** telemetry · CI exit gate · confidential-data redaction |
| **Reliability heart** | **determinism/flakiness gate** (classify stable/flaky, quarantine) · **repro bundles** (seed, config, env fingerprint, redacted logs, exact re-run command) |
| **Quality gates** | golden baselines + regression thresholds, **hardware-aware** (status/accuracy gate everywhere; raw performance only on comparable hardware) |
| **Config matrix** | run one suite across a configuration matrix; surface **config-dependent failures** |
| **Tamper-evident seals** | hash-chained results (integrity) + optional HMAC signing (authenticity); verification pinpoints the first altered result |

It drives the real Java matching engine as an external SUT, and CI proves the tamper control fires. See
[`harness/README.md`](harness/README.md).

## AI-forward, with guardrails

Built with heavy AI assistance — and the apparatus around it is the point, not a footnote:

- **Agent standards as versioned infra** — [`CLAUDE.md`](CLAUDE.md) (quality bar, guardrails, a
  low-confidence-callout protocol) and committed review subagents ([`.claude/agents/`](.claude/agents/)).
- **Deterministic gates AI output must pass** — ~570 tests incl. differential and property-based,
  CI, CodeQL, Trivy, Dependabot.
- **Auditable provenance** — AI-assisted commits carry `Co-Authored-By` trailers.
- **Accountable judgment** — a human owns every merge; uncertainty is surfaced, not hidden.

Full account: [`docs/ai-assisted-engineering.md`](docs/ai-assisted-engineering.md).

## The quality bar (what makes claims trustworthy)

- **~570 automated tests** — Java 179 (incl. jqwik property tests), Python research 320, harness 69,
  frontend 8 — run in CI across every component.
- **Differential + property tests** exist specifically to catch confidently-wrong output; every number
  in the repo is reproducible from a command, none invented.
- **Determinism** — seeded, no look-ahead, no wall-clock in analysis/test paths.
- **Security** — no committed secrets, parameterized persistence, output redaction, SAST + image +
  dependency scanning. See [`SECURITY.md`](SECURITY.md).

## Run it

```bash
cd backend && ./mvnw -B verify          # matching engine + OMS (Docker for integration tests)
cd research && python -m pytest -q      # quant engine + alpha DSL (320 tests)
python -m pytest harness -q             # validation harness (69 tests)
python -m harness --out artifacts --seal --repro-dir repro   # run the readiness lab, sealed
python run_dsl.py ; python run_sigcache.py ; python run_parallel.py ; python run_matrix.py
```
