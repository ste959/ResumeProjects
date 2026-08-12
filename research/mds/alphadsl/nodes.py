"""Abstract syntax tree for the alpha DSL.

Five immutable node types are enough to express the whole language. Each node knows how to render
itself two ways:

* :meth:`pretty` — a readable infix form (for error messages and ``__str__``).
* :meth:`canonical` — an unambiguous, fully-parenthesised prefix form. This is what the content-address
  cache hashes, so two source strings that differ only in whitespace or redundant parentheses produce
  the *same* fingerprint (and therefore the same cache key).
"""

from __future__ import annotations

from dataclasses import dataclass


class Node:
    """Base AST node."""

    def canonical(self) -> str:
        raise NotImplementedError

    def pretty(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.pretty()


@dataclass(frozen=True)
class Num(Node):
    value: float

    def canonical(self) -> str:
        # Normalise 5 and 5.0 to one spelling so they hash identically.
        v = self.value
        return repr(int(v)) if float(v).is_integer() else repr(v)

    def pretty(self) -> str:
        return self.canonical()


@dataclass(frozen=True)
class Col(Node):
    """A data column of the panel (e.g. close, volume)."""

    name: str

    def canonical(self) -> str:
        return f"col:{self.name}"

    def pretty(self) -> str:
        return self.name


@dataclass(frozen=True)
class Unary(Node):
    op: str               # only "-"
    operand: Node

    def canonical(self) -> str:
        return f"(neg {self.operand.canonical()})"

    def pretty(self) -> str:
        return f"-{self.operand.pretty()}"


@dataclass(frozen=True)
class BinOp(Node):
    op: str               # + - * / **
    left: Node
    right: Node

    def canonical(self) -> str:
        return f"({self.op} {self.left.canonical()} {self.right.canonical()})"

    def pretty(self) -> str:
        return f"({self.left.pretty()} {self.op} {self.right.pretty()})"


@dataclass(frozen=True)
class Call(Node):
    func: str
    args: tuple[Node, ...]

    def canonical(self) -> str:
        inner = " ".join(a.canonical() for a in self.args)
        return f"({self.func} {inner})"

    def pretty(self) -> str:
        inner = ", ".join(a.pretty() for a in self.args)
        return f"{self.func}({inner})"


def walk(node: Node):
    """Yield ``node`` and every descendant, pre-order."""
    yield node
    if isinstance(node, Unary):
        yield from walk(node.operand)
    elif isinstance(node, BinOp):
        yield from walk(node.left)
        yield from walk(node.right)
    elif isinstance(node, Call):
        for a in node.args:
            yield from walk(a)


def columns_used(node: Node) -> set[str]:
    """The set of data columns referenced anywhere in the expression."""
    return {n.name for n in walk(node) if isinstance(n, Col)}
