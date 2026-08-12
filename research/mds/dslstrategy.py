"""Bridge the alpha DSL into the backtest engine: a compiled signal expression becomes a first-class
:class:`~mds.engine.Strategy`, so you can write a strategy as one line of DSL and run it through the
exact same walk-forward engine, cost model, and gauntlet as the hand-coded strategies.

The signal panel is evaluated once in :meth:`prepare` (the engine's precompute hook). Reading the
signal at row ``t-1`` inside :meth:`target_weights` is causal by construction: cross-sectional
operators use only that date's cross-section, and time-series operators (``ts_*``/``delay``) look
strictly backwards — so the value as of the prior close never depends on future data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from .alphadsl import CompiledSignal, compile_signal
from .engine import Strategy

if TYPE_CHECKING:
    from .sigcache import SignalCache


class DslStrategy(Strategy):
    """Trade a DSL expression as a dollar-neutral, unit-gross book.

    The signal's cross-sectional score per name is turned into weights by demeaning (dollar neutrality)
    and L1-normalising (unit gross), which is the standard way to make a market-neutral book out of any
    cross-sectional alpha. Extra non-price panels (e.g. volume) can be supplied once at construction.
    """

    def __init__(self, expression: str, symbols: list[str], *, name: str | None = None,
                 warmup: int = 252, extra_panels: dict[str, pd.DataFrame] | None = None,
                 cache: "SignalCache | None" = None):
        self._signal_expr: CompiledSignal = compile_signal(expression)   # validates up-front
        self._symbols = list(symbols)
        self.name = name or f"dsl:{self._signal_expr.ast.pretty()}"
        self.warmup = warmup
        self._extra = extra_panels or {}
        self._cache = cache        # optional: memoize the signal panel across repeated runs/sweeps
        self._panel: pd.DataFrame | None = None

    def symbols(self) -> list[str]:
        return self._symbols

    def prepare(self, prices: pd.DataFrame) -> None:
        env: dict[str, pd.DataFrame] = {"close": prices, "returns": prices.pct_change()}
        for key, frame in self._extra.items():
            env[key] = frame.reindex(index=prices.index, columns=prices.columns)
        # Content-addressed cache when provided: identical (signal, data) → reuse, no re-evaluation.
        panel = self._cache.evaluate(self._signal_expr, env) if self._cache is not None \
            else self._signal_expr.evaluate(env)
        # A scalar-only expression (no column) isn't a tradable signal.
        if not isinstance(panel, pd.DataFrame):
            raise ValueError(f"signal {self._signal_expr.source!r} does not reference any data column")
        self._panel = panel.reindex(columns=self._symbols)

    def target_weights(self, prices: pd.DataFrame, t: int) -> np.ndarray:
        row = np.nan_to_num(self._panel.iloc[t - 1].to_numpy(dtype=float))   # signal as of the prior close
        row = row - row.mean()                                                # dollar-neutral
        gross = np.abs(row).sum()
        return row / gross if gross > 0 else row                             # unit-gross
