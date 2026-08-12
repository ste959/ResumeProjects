"""Precedence-climbing (Pratt-style) parser for the alpha DSL.

Grammar (EBNF)::

    expr    := unary (BINOP unary)*          # BINOP ∈ { + - * / }, precedence-climbing
    unary   := '-' unary | power
    power   := primary ('**' unary)?         # right-associative, binds tighter than unary minus
    primary := NUMBER
             | IDENT '(' args? ')'           # function call
             | IDENT                          # data column
             | '(' expr ')'
    args    := expr (',' expr)*

Binary precedence is a tiny table (``+ -`` below ``* /``); left-associativity falls out of passing
``prec + 1`` as the minimum binding power for the right operand. ``**`` is handled separately in
``power`` so that ``-x ** 2`` parses as ``-(x ** 2)`` — the conventional maths reading.
"""

from __future__ import annotations

from .lexer import Tok, Token, tokenize
from .nodes import BinOp, Call, Col, Node, Num, Unary

# Left-binding power of each infix operator; higher binds tighter.
_PREC = {Tok.PLUS: 10, Tok.MINUS: 10, Tok.STAR: 20, Tok.SLASH: 20}
_OP_TEXT = {Tok.PLUS: "+", Tok.MINUS: "-", Tok.STAR: "*", Tok.SLASH: "/"}


class ParseError(ValueError):
    """A syntactically malformed expression, reported with the offending column."""


class Parser:
    def __init__(self, tokens: list[Token]):
        self._toks = tokens
        self._i = 0

    # -- token cursor --------------------------------------------------------
    @property
    def _cur(self) -> Token:
        return self._toks[self._i]

    def _advance(self) -> Token:
        t = self._toks[self._i]
        self._i += 1
        return t

    def _expect(self, kind: Tok) -> Token:
        if self._cur.kind is not kind:
            raise ParseError(f"expected {kind.name} but found {self._cur.text!r} at column {self._cur.pos}")
        return self._advance()

    # -- grammar -------------------------------------------------------------
    def parse(self) -> Node:
        """Parse the full token stream into one AST, requiring it to end at EOF."""
        node = self._expr(0)
        if self._cur.kind is not Tok.EOF:
            raise ParseError(f"unexpected trailing {self._cur.text!r} at column {self._cur.pos}")
        return node

    def _expr(self, min_bp: int) -> Node:
        left = self._unary()
        while (prec := _PREC.get(self._cur.kind)) is not None and prec >= min_bp:
            op = _OP_TEXT[self._advance().kind]
            right = self._expr(prec + 1)          # +1 → left-associative
            left = BinOp(op, left, right)
        return left

    def _unary(self) -> Node:
        if self._cur.kind is Tok.MINUS:
            self._advance()
            return Unary("-", self._unary())
        return self._power()

    def _power(self) -> Node:
        base = self._primary()
        if self._cur.kind is Tok.POW:
            self._advance()
            return BinOp("**", base, self._unary())   # right-assoc; exponent may be unary
        return base

    def _primary(self) -> Node:
        t = self._cur
        if t.kind is Tok.NUMBER:
            self._advance()
            return Num(float(t.text))
        if t.kind is Tok.LPAREN:
            self._advance()
            node = self._expr(0)
            self._expect(Tok.RPAREN)
            return node
        if t.kind is Tok.IDENT:
            self._advance()
            if self._cur.kind is Tok.LPAREN:          # function call
                self._advance()
                args: list[Node] = []
                if self._cur.kind is not Tok.RPAREN:
                    args.append(self._expr(0))
                    while self._cur.kind is Tok.COMMA:
                        self._advance()
                        args.append(self._expr(0))
                self._expect(Tok.RPAREN)
                return Call(t.text, tuple(args))
            return Col(t.text)                         # bare identifier → data column
        raise ParseError(f"unexpected {t.text!r} at column {t.pos}")


def parse(src: str) -> Node:
    """Tokenize and parse ``src`` into an AST (no semantic validation — see :mod:`.compiler`)."""
    return Parser(tokenize(src)).parse()
