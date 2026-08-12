"""Lexer for the alpha-signal DSL.

Turns source text like ``rank(ts_delta(close, 5)) - 0.5 * zscore(volume)`` into a flat token stream.
Kept deliberately small and position-aware: every token carries the column where it started so the
parser and validator can point at the exact offset of a syntax or type error.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Tok(Enum):
    NUMBER = auto()
    IDENT = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    POW = auto()          # **
    LPAREN = auto()
    RPAREN = auto()
    COMMA = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    kind: Tok
    text: str
    pos: int              # 0-based column where the token starts


class LexError(ValueError):
    """A character the lexer can't start a token with."""


_SINGLE = {
    "+": Tok.PLUS,
    "-": Tok.MINUS,
    "/": Tok.SLASH,
    "(": Tok.LPAREN,
    ")": Tok.RPAREN,
    ",": Tok.COMMA,
}


def _is_ident_start(c: str) -> bool:
    return c.isalpha() or c == "_"


def _is_ident_part(c: str) -> bool:
    return c.isalnum() or c == "_"


def tokenize(src: str) -> list[Token]:
    """Scan ``src`` into tokens, ending with a single EOF. Raises :class:`LexError` on a stray char."""
    tokens: list[Token] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        if c == "*":
            if i + 1 < n and src[i + 1] == "*":   # ** binds tighter than * (see parser)
                tokens.append(Token(Tok.POW, "**", i))
                i += 2
            else:
                tokens.append(Token(Tok.STAR, "*", i))
                i += 1
            continue
        if c in _SINGLE:
            tokens.append(Token(_SINGLE[c], c, i))
            i += 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            start = i
            i += 1
            while i < n and (src[i].isdigit() or src[i] in ".eE" or
                             (src[i] in "+-" and src[i - 1] in "eE")):
                i += 1
            tokens.append(Token(Tok.NUMBER, src[start:i], start))
            continue
        if _is_ident_start(c):
            start = i
            i += 1
            while i < n and _is_ident_part(src[i]):
                i += 1
            tokens.append(Token(Tok.IDENT, src[start:i], start))
            continue
        raise LexError(f"unexpected character {c!r} at column {i}")
    tokens.append(Token(Tok.EOF, "", n))
    return tokens
