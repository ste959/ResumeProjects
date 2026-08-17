# Architecture Decision Records

Short records of the decisions that shaped this platform — the *why* behind the non-obvious calls, so a
future reader (or interviewer) doesn't have to reverse-engineer intent from the code. Each ADR states
the context, the decision, and the consequences (including what we gave up).

Format: [Michael Nygard's ADR template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

| # | Decision | Status |
|---|---|---|
| [0001](0001-transactional-outbox.md) | Transactional outbox instead of a dual write to Kafka | Accepted |
| [0002](0002-two-matching-engines.md) | Two order-book implementations, kept on purpose | Accepted |
| [0003](0003-integer-ticks-hot-path.md) | Integer ticks/lots on the matching hot path (no BigDecimal) | Accepted |
| [0004](0004-alpha-signal-dsl.md) | A compiled DSL for alpha signals (signals as data) | Accepted |
| [0005](0005-deterministic-validation-harness.md) | A deterministic validation harness with hardware-aware gates | Accepted |
| [0006](0006-tamper-evident-seals.md) | Hash-chained, optionally-signed result seals | Accepted |
| [0007](0007-ai-forward-with-guardrails.md) | AI-forward development behind committed guardrails | Accepted |
| [0008](0008-tracing-and-venue-resilience.md) | Distributed tracing + a circuit-broken venue client | Accepted |
