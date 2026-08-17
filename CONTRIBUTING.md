# Contributing

This project is **AI-forward and accountable**: generative tools accelerate the work, and a set of
deterministic gates plus human review hold the quality bar. That posture is documented in full in
[`docs/ai-assisted-engineering.md`](docs/ai-assisted-engineering.md); the operating rules for agents
live in [`CLAUDE.md`](CLAUDE.md). This file is the short workflow.

## Workflow

1. **Branch off `main`.** One focused change per branch; commits are small and individually
   narratable.
2. **Write the code and the tests together.** New logic needs tests (see the quality bar below).
3. **Run the gates locally** for every component you touched (commands below).
4. **Review before proposing done.** Run the committed review subagents — `code-reviewer` for
   correctness/simplification, `security-reviewer` for anything touching auth, I/O, config, or
   dependencies (`.claude/agents/`).
5. **Open a PR.** CI must be green. A human owns the merge.

## The quality bar

- **Tests pass and cover new logic.** Prefer the strong kinds used here: property-based, **differential**
  (a new implementation matches the reference it replaces), and determinism / no-look-ahead invariants.
- **Never weaken or delete a test** to go green.
- **Determinism** — seeded randomness only; no wall-clock in analysis/test paths.
- **CI green** across affected components, including CodeQL SAST.
- **No secrets** committed, ever.

## Commands

```bash
# Backend (Java 21) — integration tests need Docker
cd backend && ./mvnw -B verify
cd risk-service && ./mvnw -B verify

# Frontend (Node)
cd frontend && npm ci && npm test && npm run build

# Research + alpha DSL (Python)
cd research && python -m pytest -q

# Validation harness (Python, stdlib only)
python -m pytest harness -q
python -m harness --out artifacts        # runs the example suite; exits non-zero on FAIL/ERROR
```

## Commits

- Conventional-style subject (`feat(scope): …`, `fix(scope): …`, `docs: …`).
- AI-assisted commits end with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` so AI
  contribution stays auditable in the history.

## Using AI here

Use approved AI tools for implementation, test authoring, review, and docs — and **verify their
output**. Distinguish what you *confirmed* (ran the test) from what you *believe*. Flag low-confidence
work rather than smoothing it over. AI never gets to skip the gates, and a human is accountable for
every merge. See [`docs/ai-assisted-engineering.md`](docs/ai-assisted-engineering.md).
