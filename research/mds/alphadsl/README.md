# `alphadsl` — a small compiler for alpha signals

Signals in this platform used to be hand-written Python. This package makes a signal a **compiled
expression** instead — so a signal is *data*, not code. That one change buys three things: signals can
be **validated before they touch the market**, **content-addressed and cached**, and **executed in
parallel** — and it does it through a real, if small, compiler.

```
"rank(ts_delta(close, 5)) - 0.5 * zscore(volume)"
        │
        ▼   lexer.py        position-aware tokens
        ▼   parser.py       precedence-climbing (Pratt) → AST
        ▼   compiler.py     semantic analysis + content-address fingerprint
        ▼   evaluator.py    lower AST → vectorized pandas
        ▼
   date × symbol signal panel
```

## The pipeline

| Stage | File | What it does |
|---|---|---|
| **Lex** | `lexer.py` | Source → tokens, each carrying its column (for precise error offsets). Distinguishes `**` from `*`. |
| **Parse** | `parser.py` | Precedence-climbing parser. Correct precedence (`*` over `+`), left-associative `+ - * /`, right-associative `**` binding tighter than unary minus (`-x**2` = `-(x**2)`). |
| **AST** | `nodes.py` | Five immutable node types. Each renders a **canonical prefix form**; the fingerprint hashes *that*, so whitespace/paren-only differences collide to one cache key. |
| **Check** | `compiler.py` | Semantic pass: unknown function, wrong arity, non-integer/non-positive look-back windows, non-constant numeric args, unknown columns — each raised **at compile time** with the operator at fault. |
| **Eval** | `evaluator.py` | Post-order walk lowering each node to vectorized pandas. No per-row Python loop. |

## The language

Two operator families, matching the two axes an alpha combines information along:

- **Cross-sectional** (across symbols, per date): `rank`, `zscore`, `demean`, `scale`, `clip`, `abs`, `sign`, `log`
- **Time-series** (along the calendar, per symbol): `delay`, `ts_delta`, `ts_sum`, `ts_mean`, `ts_std`, `ts_zscore`, `ts_max`, `ts_min`

The registry (`operators.py`) is the single source of truth for both the checker (arity + argument
kinds) and the evaluator (implementation) — add an operator in one place and both stay in sync.

## The load-bearing test

A compiler is only trustworthy if lowering preserves meaning. The **differential test** pins the
evaluator to the hand-written factor code it replaces:

```python
evaluate("zscore(close)")                        == factors._xs_zscore(close)     # to 1e-12
evaluate("zscore(clip(zscore(close), -3, 3))")   == factors.standardize(close, 3) # to 1e-12
```

That equivalence is what lets a signal be re-expressed as an AST without changing what it computes.

## Usage

```python
from mds.alphadsl import compile_signal, evaluate

sig = compile_signal("zscore(-ts_delta(close, 5))")   # validates now, not mid-backtest
sig.fingerprint          # 'a1b2…' — stable content address
sig.columns              # {'close'}
panel = sig.evaluate({"close": close_df})

# …or run it as a market-neutral strategy through the real engine:
from mds.dslstrategy import DslStrategy
```

`python run_dsl.py` demonstrates the whole pipeline. See `tests/test_alphadsl.py` and
`tests/test_dslstrategy.py`.

## Why it's built this way (and what's next)

The fingerprint isn't decoration — it's the key for the **next layer**: a content-addressed cache that
memoizes a signal's evaluated panel on `hash(AST, data version, params)` and invalidates on any input
change (the same idea as Bazel/dbt). And because the AST is a computation graph of independent
sub-expressions, evaluation is **embarrassingly parallel** — the third layer. The compiler is the
keystone that makes both honest: *cache what's identical, parallelize what's independent.*
