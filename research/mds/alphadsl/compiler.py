"""The compiler front door: parse → semantic-check → fingerprint → :class:`CompiledSignal`.

The semantic pass is what makes this a compiler rather than a string-eval. Before any data touches it,
it proves the expression is well-formed: every function exists, arity matches, look-back windows are
positive integer constants, and (optionally) every referenced column is available. Errors are raised
at *compile time* with the operator/column at fault — not as a mid-backtest pandas traceback.

The fingerprint is a hash of the AST's canonical form, so it is invariant to whitespace and redundant
parentheses. That makes it a stable content-address key for memoising a signal's evaluated panel.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pandas as pd

from .evaluator import evaluate as _evaluate
from .nodes import BinOp, Call, Col, Node, Num, Unary, columns_used, walk
from .operators import Kind, REGISTRY
from .parser import parse as _parse


class ValidationError(ValueError):
    """A parseable expression that is semantically wrong (bad operator, arity, window, or column)."""


def _fold_const(node: Node) -> float | None:
    """Fold a constant numeric sub-expression to its value, or return None if it isn't constant.

    Constants may involve unary minus and arithmetic on literals (so ``-3`` and ``2 * 5`` are constant),
    but anything touching a data column is not — which is exactly why a window argument can't be
    ``ts_mean(close, volume)``.
    """
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Unary):
        v = _fold_const(node.operand)
        return None if v is None else -v
    if isinstance(node, BinOp):
        a, b = _fold_const(node.left), _fold_const(node.right)
        if a is None or b is None:
            return None
        return {"+": a + b, "-": a - b, "*": a * b,
                "/": (a / b if b else float("nan")), "**": a ** b}[node.op]
    return None


def validate(node: Node, columns: set[str] | None = None) -> None:
    """Semantic-analysis pass. Raises :class:`ValidationError` on the first problem it finds."""
    for n in walk(node):
        if isinstance(n, Call):
            spec = REGISTRY.get(n.func)
            if spec is None:
                raise ValidationError(f"unknown function {n.func!r}")
            if len(n.args) != spec.arity:
                raise ValidationError(
                    f"{n.func}() takes {spec.arity} argument(s), got {len(n.args)}")
            for kind, arg in zip(spec.arg_kinds, n.args):
                if kind is Kind.WINDOW:
                    v = _fold_const(arg)
                    if v is None or v <= 0 or not float(v).is_integer():
                        raise ValidationError(
                            f"{n.func}(): look-back window must be a positive integer constant, got {arg.pretty()!r}")
                elif kind is Kind.NUMBER:
                    if _fold_const(arg) is None:
                        raise ValidationError(
                            f"{n.func}(): expected a numeric constant, got {arg.pretty()!r}")
        elif isinstance(n, Col) and columns is not None and n.name not in columns:
            raise ValidationError(f"unknown column {n.name!r}; available: {sorted(columns)}")


def fingerprint(node: Node) -> str:
    """A stable 16-hex-char content address for the expression (hash of its canonical form)."""
    return hashlib.sha256(node.canonical().encode()).hexdigest()[:16]


@dataclass(frozen=True)
class CompiledSignal:
    """A parsed, validated, fingerprinted signal ready to evaluate against panel data."""

    source: str
    ast: Node
    fingerprint: str

    @property
    def columns(self) -> set[str]:
        """Data columns this signal reads — the inputs its cache key must depend on."""
        return columns_used(self.ast)

    def evaluate(self, env: dict[str, pd.DataFrame]) -> pd.DataFrame:
        return _evaluate(self.ast, env)

    def __str__(self) -> str:
        return f"CompiledSignal({self.ast.pretty()}  #{self.fingerprint})"


def compile_signal(source: str, columns: set[str] | None = None) -> CompiledSignal:
    """Parse, validate, and fingerprint ``source``. Pass ``columns`` to check references early."""
    ast = _parse(source)
    validate(ast, columns)
    return CompiledSignal(source, ast, fingerprint(ast))


def evaluate(source: str, env: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Convenience: compile ``source`` (validating columns against ``env``) and evaluate it."""
    return compile_signal(source, columns=set(env)).evaluate(env)
