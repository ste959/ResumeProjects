"""Operator registry for the alpha DSL — the single source of truth for both the semantic checker
and the evaluator.

Every function is declared once with its argument *kinds*:

* ``SERIES``  — an arbitrary sub-expression that evaluates to a panel (date × symbol DataFrame).
* ``WINDOW``  — a look-back length; must be a positive **integer literal** (checked at compile time).
* ``NUMBER``  — a scalar numeric literal.

The implementations are all vectorised pandas — no per-row Python loops. Cross-sectional operators act
across symbols (``axis=1``, one value per date); time-series operators act along the calendar
(``axis=0``, rolling per symbol). The two axes are exactly the two ways an alpha combines information,
so the operator set stays small but expressive.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

import numpy as np
import pandas as pd


class Kind(Enum):
    SERIES = auto()
    WINDOW = auto()
    NUMBER = auto()


@dataclass(frozen=True)
class OpSpec:
    name: str
    arg_kinds: tuple[Kind, ...]
    fn: Callable[..., pd.DataFrame]
    doc: str

    @property
    def arity(self) -> int:
        return len(self.arg_kinds)


# ---- cross-sectional operators (act across symbols, per date) ---------------

def _rank(x: pd.DataFrame) -> pd.DataFrame:
    return x.rank(axis=1, pct=True)                       # percentile rank in (0, 1]


def _zscore(x: pd.DataFrame) -> pd.DataFrame:
    # Matches mds.factors._xs_zscore exactly (sample std, ddof=1; 0-std days → NaN).
    mean = x.mean(axis=1)
    std = x.std(axis=1).replace(0, np.nan)
    return x.sub(mean, axis=0).div(std, axis=0)


def _demean(x: pd.DataFrame) -> pd.DataFrame:
    return x.sub(x.mean(axis=1), axis=0)


def _scale(x: pd.DataFrame) -> pd.DataFrame:
    # Normalise each date to unit gross (L1) exposure — the usual "book of size 1" convention.
    return x.div(x.abs().sum(axis=1), axis=0)


def _clip(x: pd.DataFrame, lo: float, hi: float) -> pd.DataFrame:
    return x.clip(lower=lo, upper=hi)


# ---- time-series operators (act along the calendar, per symbol) -------------

def _delay(x: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.shift(d)


def _ts_delta(x: pd.DataFrame, d: int) -> pd.DataFrame:
    return x - x.shift(d)


def _ts_sum(x: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.rolling(d).sum()


def _ts_mean(x: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.rolling(d).mean()


def _ts_std(x: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.rolling(d).std()


def _ts_zscore(x: pd.DataFrame, d: int) -> pd.DataFrame:
    roll = x.rolling(d)
    return (x - roll.mean()) / roll.std()


def _ts_max(x: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.rolling(d).max()


def _ts_min(x: pd.DataFrame, d: int) -> pd.DataFrame:
    return x.rolling(d).min()


_S, _W, _N = Kind.SERIES, Kind.WINDOW, Kind.NUMBER

REGISTRY: dict[str, OpSpec] = {
    op.name: op for op in [
        OpSpec("rank", (_S,), _rank, "cross-sectional percentile rank in (0,1]"),
        OpSpec("zscore", (_S,), _zscore, "cross-sectional z-score (demean/scale across names)"),
        OpSpec("demean", (_S,), _demean, "subtract the cross-sectional mean each date"),
        OpSpec("scale", (_S,), _scale, "normalise to unit gross (L1) exposure each date"),
        OpSpec("clip", (_S, _N, _N), _clip, "clip values to [lo, hi]"),
        OpSpec("abs", (_S,), lambda x: x.abs(), "elementwise absolute value"),
        OpSpec("sign", (_S,), lambda x: np.sign(x), "elementwise sign (-1/0/+1)"),
        OpSpec("log", (_S,), lambda x: np.log(x), "elementwise natural log"),
        OpSpec("delay", (_S, _W), _delay, "value d periods ago"),
        OpSpec("ts_delta", (_S, _W), _ts_delta, "change over d periods (x - x[-d])"),
        OpSpec("ts_sum", (_S, _W), _ts_sum, "rolling sum over d periods"),
        OpSpec("ts_mean", (_S, _W), _ts_mean, "rolling mean over d periods"),
        OpSpec("ts_std", (_S, _W), _ts_std, "rolling std over d periods"),
        OpSpec("ts_zscore", (_S, _W), _ts_zscore, "rolling z-score over d periods"),
        OpSpec("ts_max", (_S, _W), _ts_max, "rolling max over d periods"),
        OpSpec("ts_min", (_S, _W), _ts_min, "rolling min over d periods"),
    ]
}
