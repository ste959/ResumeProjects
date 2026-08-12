"""Tests for the alpha-signal DSL compiler.

Three things must hold for this to be trustworthy: it parses the grammar correctly (precedence,
associativity), it rejects malformed/ill-typed programs at compile time, and — the load-bearing one —
its evaluator computes exactly what the hand-written factor code computes (the differential test).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mds import alphadsl as dsl
from mds import factors as fc
from mds.alphadsl.nodes import BinOp, Call, Col, Num, Unary


# ---------------------------------------------------------------- fixtures ---
def _panel(seed, cols=("A", "B", "C", "D", "E"), n=60):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2021-01-01", periods=n)
    return pd.DataFrame(rng.normal(size=(n, len(cols))), index=idx, columns=list(cols))


@pytest.fixture
def env():
    return {"close": _panel(0) + 100, "volume": _panel(1).abs() + 1}


# ------------------------------------------------------------------- lexer ---
def test_lexer_distinguishes_star_and_pow():
    kinds = [t.kind.name for t in dsl.tokenize("a ** b * c")]
    assert kinds == ["IDENT", "POW", "IDENT", "STAR", "IDENT", "EOF"]


def test_lexer_rejects_stray_character():
    with pytest.raises(dsl.LexError):
        dsl.tokenize("close @ volume")


# ------------------------------------------------------------------ parser ---
def test_precedence_multiplication_binds_tighter_than_addition():
    ast = dsl.parse("a + b * c")
    assert isinstance(ast, BinOp) and ast.op == "+"
    assert isinstance(ast.right, BinOp) and ast.right.op == "*"   # b*c grouped


def test_subtraction_is_left_associative():
    ast = dsl.parse("a - b - c")                                  # (a - b) - c
    assert isinstance(ast.left, BinOp) and ast.left.op == "-"


def test_power_is_right_associative_and_binds_tighter_than_unary_minus():
    ast = dsl.parse("-a ** 2")                                    # -(a ** 2)
    assert isinstance(ast, Unary) and isinstance(ast.operand, BinOp) and ast.operand.op == "**"
    r = dsl.parse("a ** b ** c")                                  # a ** (b ** c)
    assert isinstance(r.right, BinOp) and r.right.op == "**"


def test_bare_identifier_is_a_column_call_is_a_call():
    assert isinstance(dsl.parse("close"), Col)
    node = dsl.parse("ts_mean(close, 5)")
    assert isinstance(node, Call) and node.func == "ts_mean" and len(node.args) == 2


def test_parser_reports_trailing_and_unbalanced():
    with pytest.raises(dsl.ParseError):
        dsl.parse("close 5")
    with pytest.raises(dsl.ParseError):
        dsl.parse("rank(close")


# ------------------------------------------------ canonical / fingerprint ---
def test_fingerprint_is_invariant_to_whitespace_and_parens():
    a = dsl.compile_signal("zscore(ts_delta(close,5))").fingerprint
    b = dsl.compile_signal("  zscore( ts_delta( close , 5 ) )  ").fingerprint
    c = dsl.compile_signal("(zscore(ts_delta(close, 5)))").fingerprint
    assert a == b == c


def test_fingerprint_distinguishes_different_expressions():
    assert dsl.compile_signal("ts_delta(close, 5)").fingerprint != \
           dsl.compile_signal("ts_delta(close, 6)").fingerprint


def test_integer_and_float_literals_normalise():
    assert dsl.compile_signal("ts_mean(close, 5)").fingerprint == \
           dsl.compile_signal("ts_mean(close, 5.0)").fingerprint


def test_columns_used():
    assert dsl.compile_signal("rank(close) - zscore(volume)").columns == {"close", "volume"}


# -------------------------------------------------------------- validation ---
@pytest.mark.parametrize("src, msg", [
    ("foo(close)", "unknown function"),
    ("zscore(close, 5)", "argument"),
    ("ts_mean(close, -5)", "positive integer"),
    ("ts_mean(close, 2.5)", "positive integer"),
    ("ts_mean(close, volume)", "positive integer"),
    ("clip(close, price, 3)", "numeric constant"),
])
def test_validation_rejects_ill_typed_programs(src, msg):
    with pytest.raises(dsl.ValidationError) as e:
        dsl.compile_signal(src, columns={"close", "volume"})
    assert msg in str(e.value)


def test_validation_flags_unknown_column_when_columns_known():
    with pytest.raises(dsl.ValidationError):
        dsl.compile_signal("rank(price)", columns={"close", "volume"})


def test_constant_folding_allows_arithmetic_windows():
    # A window may be a constant expression, not just a literal.
    dsl.compile_signal("ts_mean(close, 2 * 5)", columns={"close"})


# --------------------------------------------------------------- evaluator ---
def test_binary_ops_and_broadcasting(env):
    got = dsl.evaluate("close * 2 - 1", env)
    pd.testing.assert_frame_equal(got, env["close"] * 2 - 1)


def test_cross_sectional_operators(env):
    c = env["close"]
    pd.testing.assert_frame_equal(dsl.evaluate("rank(close)", env), c.rank(axis=1, pct=True))
    pd.testing.assert_frame_equal(dsl.evaluate("demean(close)", env), c.sub(c.mean(axis=1), axis=0))
    pd.testing.assert_frame_equal(dsl.evaluate("clip(close, 99, 101)", env), c.clip(99, 101))


def test_time_series_operators(env):
    c = env["close"]
    pd.testing.assert_frame_equal(dsl.evaluate("delay(close, 3)", env), c.shift(3))
    pd.testing.assert_frame_equal(dsl.evaluate("ts_delta(close, 5)", env), c - c.shift(5))
    pd.testing.assert_frame_equal(dsl.evaluate("ts_mean(close, 10)", env), c.rolling(10).mean())
    pd.testing.assert_frame_equal(dsl.evaluate("ts_std(close, 10)", env), c.rolling(10).std())


def test_scale_gives_unit_gross_exposure(env):
    w = dsl.evaluate("scale(demean(close))", env).dropna()
    assert np.allclose(w.abs().sum(axis=1), 1.0)


def test_evaluate_raises_on_unknown_column_without_precheck():
    with pytest.raises(dsl.EvalError):
        dsl.compile_signal("rank(price)").evaluate({"close": _panel(0)})


# ------------------------------------------- DIFFERENTIAL TEST vs factors.py --
# The evaluator must compute exactly what the hand-written factor code computes. This is the
# correctness invariant that lets a signal be expressed as data (an AST) without changing its meaning.
def test_dsl_zscore_matches_factors_xs_zscore(env):
    got = dsl.evaluate("zscore(close)", env)
    expected = fc._xs_zscore(env["close"])
    assert np.allclose(got.values, expected.values, equal_nan=True, atol=1e-12)


def test_dsl_reproduces_factors_standardize(env):
    got = dsl.evaluate("zscore(clip(zscore(close), -3, 3))", env)
    expected = fc.standardize(env["close"], winsor=3.0)
    assert np.allclose(got.values, expected.values, equal_nan=True, atol=1e-12)


def test_dsl_reproduces_a_short_reversal_signal(env):
    # 5-day reversal, cross-sectionally standardized — two spellings, identical result.
    got = dsl.evaluate("zscore(-ts_delta(close, 5))", env)
    c = env["close"]
    expected = fc._xs_zscore(-(c - c.shift(5)))
    assert np.allclose(got.values, expected.values, equal_nan=True, atol=1e-12)
