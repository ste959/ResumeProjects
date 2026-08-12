"""Evaluator — lowers a validated AST to vectorised pandas over a panel environment.

The environment maps column names to aligned ``date × symbol`` DataFrames (``{"close": ..., "volume":
...}``). Evaluation is a straightforward post-order walk: operands are computed first, then the node
combines them. Binary operators lean on pandas' own broadcasting (panel⊕panel aligns on index and
columns; panel⊕scalar broadcasts), so there is no hand-written elementwise loop anywhere.
"""

from __future__ import annotations

import operator

import pandas as pd

from .nodes import BinOp, Call, Col, Node, Num, Unary
from .operators import Kind, REGISTRY

_BINOPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "**": operator.pow,
}


class EvalError(ValueError):
    """A reference to a column not present in the environment, etc."""


def evaluate(node: Node, env: dict[str, pd.DataFrame]):
    """Evaluate ``node`` against ``env``. Returns a DataFrame (a signal panel) or a scalar."""
    if isinstance(node, Num):
        return node.value

    if isinstance(node, Col):
        if node.name not in env:
            raise EvalError(f"unknown column {node.name!r}; available: {sorted(env)}")
        return env[node.name]

    if isinstance(node, Unary):
        return -evaluate(node.operand, env)

    if isinstance(node, BinOp):
        return _BINOPS[node.op](evaluate(node.left, env), evaluate(node.right, env))

    if isinstance(node, Call):
        spec = REGISTRY[node.func]           # existence guaranteed by validation
        values = []
        for kind, arg in zip(spec.arg_kinds, node.args):
            v = evaluate(arg, env)
            if kind is Kind.WINDOW:
                v = int(v)                   # look-back length is an integer number of periods
            values.append(v)
        return spec.fn(*values)

    raise EvalError(f"cannot evaluate node of type {type(node).__name__}")
