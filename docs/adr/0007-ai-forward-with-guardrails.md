# 7. AI-forward development behind committed guardrails

**Status:** Accepted

## Context
This project was built with heavy AI assistance. That can read as a liability ("a black box of unknown
files") or a strength — the difference is whether the apparatus around the AI is visible and enforced.

## Decision
Treat AI as an accelerator wrapped in guardrails, and make the apparatus version-controlled:
- **Agent standards as code** — `CLAUDE.md` (the quality bar, guardrails, a low-confidence-callout
  protocol) and committed review subagents (`.claude/agents/`).
- **Deterministic gates AI output must pass** — ~570 tests including differential and property-based,
  CI, CodeQL, Trivy, Dependabot.
- **Auditable provenance** — AI-assisted commits carry a `Co-Authored-By` trailer.
- **Accountable review** — a human owns every merge; uncertainty is surfaced, not hidden.

## Consequences
- **Gain:** AI-assisted velocity with a rigor you can inspect; the quality bar is exactly the one a
  modern team states ("AI assists; reproducible tests and reviewed code decide what ships").
- **Cost:** maintaining the standards and gates is real work — but it's the work that makes the AI use
  trustworthy.
- See [`docs/ai-assisted-engineering.md`](../ai-assisted-engineering.md) for the full account.
