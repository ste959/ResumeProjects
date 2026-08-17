# 5. A deterministic validation harness with hardware-aware gates

**Status:** Accepted

## Context
The platform needed a way to validate its systems the way a hardware readiness lab validates devices:
packaged scenarios, comparable results across machines, and gates that catch regressions — without the
false confidence of naive assertions.

## Decision
Build a dependency-free harness (`harness/`): declarative scenario collateral, pluggable adapters
(in-process and external-subprocess with a `LAB_RESULT` contract), a deterministic runner, NDJSON +
JUnit telemetry, a determinism/flakiness gate, repro bundles, and golden-baseline regression gates. The
regression gate is **hardware-aware**: status and accuracy (a seeded computation) are gated on every
machine, but raw performance is gated only on comparable hardware — across a CPU mismatch a throughput
delta is a drift *note*, not a failure.

## Consequences
- **Gain:** an honest "comparable results across an ecosystem" story; failures ship with a reproduction;
  flaky tests are quarantined rather than tolerated.
- **Cost:** the harness is another system to test (69 tests) — but it's pure stdlib, so it runs anywhere.
- **Alternative rejected:** treating a throughput number from one machine as a portable gate — it would
  produce false regressions across heterogeneous hardware, the opposite of the goal.
