# 4. A compiled DSL for alpha signals (signals as data)

**Status:** Accepted

## Context
Research signals started as hand-written Python functions. That makes them opaque to the platform: you
can't validate a signal before it runs, cache its result reliably, or reason about it as data.

## Decision
Give signals a small language — `rank(ts_delta(close, 5)) - 0.5 * zscore(volume)` — compiled through
**lex → Pratt parse → semantic check → evaluate** (`research/mds/alphadsl`). A signal becomes a
fingerprinted AST, which enables the two layers on top: a content-addressed cache keyed on the AST hash,
and parallel evaluation of independent signals. A **differential test** pins the evaluator to the
hand-written reference (`factors.standardize`) to 1e-12, so lowering can't silently change meaning.

## Consequences
- **Gain:** signals are validated at compile time, cached precisely, and executed in parallel; the
  compiler is the keystone the cache and parallel runner build on.
- **Cost:** a real compiler to maintain (lexer/parser/checker/evaluator + operator registry); the
  language is deliberately small (16 operators) to keep that cost bounded.
- **Alternative rejected:** `eval()` of Python strings — a security and correctness hazard, and it
  wouldn't give a stable AST to hash or validate.
