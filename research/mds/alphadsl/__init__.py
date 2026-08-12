"""A small compiler for alpha signals.

Signals are written as expressions over a panel of aligned time-series — e.g.

    rank(ts_delta(close, 5)) - 0.5 * zscore(volume)

and compiled through the standard pipeline: **lex → parse (Pratt) → semantic-check → evaluate**. The
result is that a signal becomes *data* (a fingerprinted AST) instead of code: it can be validated
before it touches the market, hashed for content-addressed caching, and lowered to vectorised pandas.

Public API::

    from mds.alphadsl import compile_signal, evaluate, parse

    sig = compile_signal("zscore(ts_delta(close, 5))")
    sig.fingerprint            # stable content address
    sig.columns                # {"close"}
    panel = sig.evaluate({"close": close_df})

    panel = evaluate("rank(volume)", {"volume": volume_df})   # one-shot
"""

from __future__ import annotations

from .compiler import CompiledSignal, ValidationError, compile_signal, evaluate, fingerprint, validate
from .evaluator import EvalError
from .lexer import LexError, tokenize
from .nodes import Node, columns_used
from .operators import REGISTRY
from .parser import ParseError, parse

__all__ = [
    "compile_signal", "evaluate", "parse", "validate", "fingerprint", "tokenize",
    "CompiledSignal", "Node", "columns_used", "REGISTRY",
    "LexError", "ParseError", "ValidationError", "EvalError",
]


def operators() -> dict[str, str]:
    """Name → one-line doc for every operator the language supports (for help/introspection)."""
    return {name: spec.doc for name, spec in REGISTRY.items()}
