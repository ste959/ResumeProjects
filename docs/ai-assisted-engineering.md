# AI-Assisted Engineering

This project was built with heavy use of AI coding tools (Claude Code), and it says so on purpose. The
interesting question in 2026 is not *whether* an engineer uses AI — the capable ones do — but whether
they use it the way a professional team does: **as an accelerator wrapped in guardrails, gates, and
accountable human judgment.** This document is the honest account of how that works here, so the code
can be trusted and the process can be inspected.

> The quality bar, stated plainly: **AI accelerates the work; deterministic tests, reviewed code, and
> accountable engineering judgment decide what ships.** An AI-generated change that fails a gate does
> not merge, no matter how plausible it looks.

## How AI is actually used

- **Implementation** — most code was drafted with AI assistance, then read, run, and revised.
- **Test authoring** — tests are written alongside features, favoring the kinds that catch real
  regressions (property-based, differential, determinism invariants).
- **Review** — committed review subagents (`.claude/agents/`) inspect changes for correctness and
  security before they're proposed as done.
- **Diagnostics & docs** — log/failure analysis and documentation are AI-accelerated, then verified.

None of that removes the engineer from the loop. It changes *where* the engineering happens: less time
typing boilerplate, more time on decomposition, verification, and judgment — which is where the
durable skill is moving.

## The guardrails that keep it honest

The point of AI-forward engineering is not speed at the expense of rigor — it's speed *plus* a rigor
you can prove. Every AI-assisted change passes through:

| Gate | What it enforces |
|---|---|
| **Automated tests** (400+ across Java/Python/TS) | correctness; new logic ships with coverage |
| **Differential tests** | a new implementation must equal the reference it replaces (e.g. the alpha-DSL evaluator vs `factors.py`, to 1e-12) |
| **Property-based tests** (jqwik) | invariants hold across generated inputs, not just examples |
| **Determinism invariants** | seeded runs reproduce; no look-ahead; no wall-clock in analysis paths |
| **CI** (`.github/workflows/`) | the full suite runs on every push/PR across all components |
| **CodeQL + Trivy + Dependabot** | SAST, image scanning, and dependency updates |
| **Committed review subagents** | correctness and security review before merge |
| **Human review** | a person owns every merge |

If AI writes something wrong, one of these catches it — and the ones that matter most (differential and
property tests) were themselves designed to make "confidently wrong" output visible.

## Accountability and provenance

- **Provenance is auditable.** AI-assisted commits carry a `Co-Authored-By` trailer, so the history
  records where AI contributed. (`git log --grep='Co-Authored-By: Claude'`.)
- **A human is accountable** for every merge — for the decomposition, the verification, and the
  decision that a change is correct and safe.
- **Low-confidence is surfaced, not hidden.** The operating rules (`CLAUDE.md`) require distinguishing
  *verified* from *believed*, flagging assumptions, and escalating genuine decisions rather than
  quietly guessing. An honest "this path only runs in CI, I couldn't verify it locally" is required over
  false confidence.

## What AI does *not* decide

- **What to build and why** — product/architecture judgment stays with the engineer.
- **Whether a result is real** — claims are verified by running the code, not asserted. Numbers in this
  repo are reproducible from a command; none are invented.
- **The trade-offs** — where a decision has no clear default (scope, a perf-vs-safety call), it's made
  by a person, on the record.

## Data handling

AI tools are used without sending secrets or confidential data to any external service. Credentials live
in git-ignored files; captured logs and telemetry are redacted before storage
(`harness/telemetry.py`). See [`SECURITY.md`](../SECURITY.md).

## Why this is a strength, not a shortcut

A repository that hides its AI use tells you nothing about the engineer. This one shows the whole
apparatus: the gates an AI change must pass, the review that inspects it, the provenance that records
it, and the human judgment that owns it. That is how software is increasingly built in professional
settings — and being able to *design and run that apparatus* is the skill, not avoiding the tools.
