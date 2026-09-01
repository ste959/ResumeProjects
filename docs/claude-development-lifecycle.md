# The Claude Development Lifecycle (CDL)

A team doesn't trust code because it was typed by a human; it trusts code because it went through a
**process** — requirements, design review, implementation, test, code review, release — with a person
accountable at each stage. AI-assisted work deserves the same. This document is that process: the
repeatable loop every non-trivial change in this repo runs through when it's built with Claude Code.

It is the companion to [`ai-assisted-engineering.md`](ai-assisted-engineering.md). That document states
the **philosophy and the gates** — *why* AI-built code here can be trusted. This one is the **workflow** —
*how* the work actually moves, phase by phase, and where the human judgment lives in each phase.

> **The thesis.** Claude is treated like a new primitive in the toolchain — closer to a compiler or a
> power tool than to a replacement for the engineer. You learn its failure modes, you wrap it in
> verification, and you stay accountable for what it produces. Used that way, AI is an accelerator with
> a rigor you can *prove*; used the other way — output trusted because it "looks right" — it is a
> liability. The difference is entirely process. This is the process.

## The lifecycle at a glance

| # | Phase | SDLC analogue | Who leads | Exit gate / artifact |
|---|---|---|---|---|
| 1 | **Frame** — goals, scope, constraints, done-criteria | Requirements | Human | A scoped statement + explicit acceptance criteria |
| 2 | **Context & prompt design** — load the contract + right files, write the instruction | Design inputs | Human | Claude has the constraints and context it needs |
| 3 | **Plan review** — Claude proposes an approach; interrogate and iterate *before* code | Design | Both | An agreed plan; no implementation starts until it holds |
| 4 | **Implement & monitor** — small steps, watched, corrected in-flight | Build | Claude | Working change, built in narratable increments |
| 5 | **Verify** — run it; show real output, never "should work" | Test | Both | Tests/build pass locally and in CI, with evidence |
| 6 | **Summarize & attribute** — what changed, why, and by whom | Docs / PR | Both | Small commits, honest summary, AI co-authorship |
| 7 | **Audit & triage** — human review + adversarial AI audit, then prioritize and loop | Review / maintenance | Both | Findings ranked; fix-now vs. backlog decided → back to 1 |

The loop is the point. A finding from Phase 7 becomes the scope of Phase 1 on the next turn.

---

## 1 — Frame the work

**Intent.** Turn a vague ask into a bounded problem before any prompt is written. What is the goal, what
is explicitly out of scope, what constraints apply (determinism, no secrets, match surrounding code),
and *how will we know it's done*?

**Human's job.** Own this phase outright. Scope and product decisions are not delegated to the model —
see [*What AI does not decide*](ai-assisted-engineering.md). If a genuine trade-off has no clear default,
it gets escalated to a person, not silently resolved by the tool.

**Claude's job.** Ask clarifying questions; surface ambiguities and hidden constraints; propose options
with a recommendation — but not choose.

**Exit gate.** A one-paragraph scoped statement with acceptance criteria you could hand to a reviewer.

---

## 2 — Context & prompt design

**Intent.** Prompting is an engineering skill, not a wish. The model can only be as good as the context
and constraints it's given, so this phase is deliberate: load the operating contract
([`CLAUDE.md`](../CLAUDE.md)), point at the relevant files, and state the constraints up front rather
than correcting for them later.

**Human's job.** Choose the context. Pick the mode/agent for the job (a focused implementation prompt, a
read-only exploration, or one of the committed review subagents in [`.claude/agents/`](../.claude/agents)).
Encode the non-negotiables — determinism, "verify don't assert," don't clobber existing tests — because
they're cheaper to state than to unwind.

**Claude's job.** Work within the loaded contract; flag when it lacks context it needs instead of
guessing.

**Exit gate.** Claude has the constraints and the code context to plan against — not a blank slate.

---

## 3 — Plan review and iteration

**Intent.** Catch a bad approach when it costs a sentence to fix, not a hundred lines. Claude proposes an
approach; it is interrogated and revised *before* implementation begins.

**Human's job.** Read the plan adversarially. Does it touch the right files? Does it respect the
architecture (persistence types stay out of the engine core; integer arithmetic on hot paths)? Does it
add tests? Iterate until the plan is sound — this is design review, and it is where the leverage is.

**Claude's job.** Lay out the steps, the files it will change, and the risks; revise on feedback.

**Exit gate.** An agreed plan. Implementation does not start on a plan that hasn't survived review.

---

## 4 — Implement and monitor

**Intent.** Build the change in small, observable increments — not a single opaque dump.

**Human's job.** Watch the work as it happens. Intervene when it drifts. Keep changes small enough that
each one is something you could walk an interviewer through.

**Claude's job.** Implement in steps; match the surrounding code's naming, structure, and comment
density; run things as it goes rather than assuming.

**Exit gate.** A working change, assembled in increments that map cleanly to commits.

---

## 5 — Verify

**Intent.** This is the gate that separates this process from vibe-coding. Nothing is "done" because it
looks right — it is done because it was **run** and the output is shown. Verified ("confirmed by running
the test") is held distinct from believed ("I expect this holds because…"), and unverifiable claims are
surfaced honestly rather than smoothed over.

**Both jobs.** Run the tests, the build, the benchmark — for real. Show the output. If a step can't run
locally (the Docker-only integration tests), say so explicitly and note that it runs in CI. Never
fabricate a number or a result.

**Exit gate.** The [gates in `ai-assisted-engineering.md`](ai-assisted-engineering.md#the-guardrails-that-keep-it-honest)
pass — tests, differential/property invariants, determinism, CI, CodeQL/Trivy — with evidence.

> **In practice.** Asked to "reverify all the numbers" in the résumé and docs, this phase re-ran the JMH
> harness instead of trusting the existing figure — and found the matching engine benchmarked at ~8M
> ops/s, not the ~3M that had been claimed. The under-claim was corrected everywhere and a committed
> benchmark artifact was added. The process caught *the AI's own unverified number*, which is exactly
> what it's for.

---

## 6 — Summarize and attribute

**Intent.** Make the change legible and its provenance honest.

**Both jobs.** Commit in small, individually narratable units. Write a summary that says what changed and
*why* (comments and messages explain intent, not mechanics). Report failures and skipped steps plainly.
End AI-assisted commits with `Co-Authored-By: Claude Opus 4.8` — attribution is a feature here, not
something to hide.

**Exit gate.** A reviewer can reconstruct what happened and who did it from the history alone.

---

## 7 — Audit, triage, and iterate

**Intent.** A second, adversarial pass — because the author (human or AI) is the worst reviewer of their
own work — and then a disciplined decision about what to do with what it finds.

**Human review.** A person owns the merge. Full stop. Nothing ships on AI judgment alone.

**AI audit.** The committed review subagents run as an independent check: [`code-reviewer`](../.claude/agents/code-reviewer.md)
for correctness and simplification, [`security-reviewer`](../.claude/agents/security-reviewer.md) for
authz/secrets/injection/deserialization/dependency hygiene, [`test-author`](../.claude/agents/test-author.md)
for coverage gaps. Crucially, the reviewer is a *different* context from the author — an adversarial
second opinion, not the same model rubber-stamping itself.

**Triage.** Findings are ranked by severity; fix-now is separated from backlog
([`docs/follow-ups.md`](follow-ups.md)). Then the highest-priority item becomes the scope of Phase 1 —
the loop closes.

> **In practice.** Running `security-reviewer` against the new identity/token layer surfaced five
> findings (three MEDIUM — a backtest authorization gap, a login timing oracle, an over-broad endpoint
> matcher; two LOW — a Redis rotate race and unbounded in-memory token growth). All five were fixed and
> re-verified before the work was called done. Separately, when CI went red across four jobs, each
> failure was root-caused, fixed, and confirmed green in CI one commit at a time — audit and triage as a
> live loop, not a one-time checkbox.

---

## Accountability: who owns what

AI accelerates every phase; it is accountable for none of them. The mapping is deliberate:

- **The human owns:** scope, product and architecture decisions, the merge, and the truth of every claim
  that ships. Confident-but-wrong is the failure mode that matters most, so the human's job is to demand
  verification and to prefer the smaller bulletproof claim over the larger shaky one.
- **Claude owns:** drafting, breadth, mechanical correctness within a stated contract, and tireless
  second-pass review — the things a power tool is good at.

If a change is wrong, the process failed, and the process is the engineer's responsibility. That is the
whole point of writing it down.

## Anti-patterns this process exists to prevent

- **Trusting output because it looks right.** Plausibility is not correctness. Phase 5 exists for this.
- **Fabricated or unverified numbers.** Benchmarks, test outcomes, and metrics are run and shown, never
  asserted.
- **The author reviewing themselves.** Phase 7 uses an independent context and a human owner.
- **Silent scope decisions.** Genuine trade-offs are escalated (Phase 1), not resolved by the tool.
- **Large, opaque changes.** Work is decomposed and monitored (Phases 3–4, 6) so every step is
  reviewable and narratable.
- **Weakening a test to go green.** Never; a failing gate is signal, not an obstacle.

## Why this is how professionals work

Strip out the word "Claude" and this is just a disciplined SDLC: requirements, design review,
implementation, test, code review, release, iterate — with clear ownership and hard gates. That's the
point. The maturity isn't in using AI; it's in refusing to let AI erode the process that makes software
trustworthy. The tool got faster. The bar did not move.
