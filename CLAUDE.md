# CLAUDE.md — operating standards for AI-assisted work in this repo

This file is the contract for any AI agent (or engineer) working in this repository. It encodes the
quality bar, the guardrails, and the conventions. **AI accelerates the work; deterministic tests,
reviewed code, and accountable human judgment remain the quality bar.** Nothing merges that a human
has not reviewed and that the gates below do not pass.

## The repository

A polyglot platform with three cooperating parts and a validation layer:

| Area | Path | Stack | How to test |
|---|---|---|---|
| OMS + matching engine | `backend/` | Java 21, Spring Boot | `cd backend && ./mvnw -B verify` (integration tests need Docker) |
| Risk service | `risk-service/` | Java 21, Spring Boot, Kafka | `cd risk-service && ./mvnw -B verify` |
| Trader UI | `frontend/` | React 18, TypeScript, Vite | `cd frontend && npm ci && npm test && npm run build` |
| Quant research + alpha DSL | `research/` | Python 3.12, pandas | `cd research && python -m pytest -q` |
| Validation harness | `harness/` | Python (stdlib only) | `python -m pytest harness -q` · `python -m harness` |

CI (`.github/workflows/ci.yml`, `codeql.yml`) runs all of the above plus CodeQL SAST and Trivy on push/PR.

## The quality bar (the gates AI output must pass)

1. **Tests pass.** Add tests for new logic; never delete or weaken a test to make a build green. Prefer
   the strong kinds already used here: **property-based** (jqwik in Java), **differential** (a new
   implementation must match the one it replaces — e.g. the DSL evaluator vs `factors.py`), and
   **determinism** invariants (seeded; no look-ahead).
2. **CI stays green** across every affected component, including CodeQL.
3. **Determinism is preserved.** Seeded randomness only; no wall-clock or unseeded nondeterminism in
   analysis/test paths. A result must be reproducible.
4. **Reviewed.** A human owns the merge. Use the committed review subagents (`.claude/agents/`) before
   proposing a change as done.

## Guardrails (must / must-never)

- **Verify, don't assert.** Run the code. Say "I ran X and it passed," not "this should work." Never
  fabricate numbers, benchmark results, or test outcomes. If something is unverified (e.g. Docker-only
  integration tests can't run locally), **say so explicitly** and note it runs in CI.
- **Report failures honestly.** If tests fail, show the output. If a step was skipped, say which and
  why. Do not paper over a limitation.
- **Never commit secrets.** `.env`, keys, and tokens are git-ignored and must stay that way. Do not send
  secrets or confidential data to any external service. Captured logs are redacted before storage
  (`harness/telemetry.py`).
- **Don't clobber existing work.** Read a file before overwriting it. Never replace a pre-existing test
  file wholesale — add a new one. (This has bitten us: service-engine tests were once overwritten.)
- **Branch, don't push to main.** Feature work goes on a branch off `main`; commits are small and
  individually narratable (each one is something you could walk an interviewer through).
- **Attribute AI contribution.** End AI-assisted commit messages with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## Low-confidence protocol (call out uncertainty)

Confident-but-wrong is the failure mode that matters most. So:

- **Flag uncertainty explicitly.** Distinguish *verified* ("confirmed by running the test") from
  *believed* ("I expect this holds because…"). Mark assumptions.
- **Surface unverified claims** rather than smoothing them over — an honest "I could not verify the
  Postgres path locally; it runs in CI" beats false confidence.
- **Escalate genuine decisions.** When a choice is the user's to make (scope, product behavior, a
  trade-off with no clear default), ask — don't silently pick and present it as settled.
- **Prefer the smaller, bulletproof claim** over the larger, shaky one. This applies to code, docs,
  and résumé language alike.

## Coding conventions

- **Match the surrounding code** — its naming, structure, and comment density. Comments explain *why*,
  not *what*; this repo favors purposeful, well-written docstrings over sparse code.
- **Java:** immutability and records where natural; integer tick/lot arithmetic on hot paths (no
  `BigDecimal` in matching loops); persistence types stay out of the engine core.
- **Python:** type hints on public APIs; separate pure, testable cores from I/O and network; vectorize
  over pandas rather than Python loops; deterministic and seeded.
- **TypeScript:** typed (no stray `any`); accessible components (semantic elements, keyboard support).

## Working style

When the task is substantial, decompose it, state the plan, and verify each step. When it is trivial,
just do it. Read `CONTRIBUTING.md` for the contribution workflow and
`docs/ai-assisted-engineering.md` for how AI is used here and why that is a strength, not a shortcut.
