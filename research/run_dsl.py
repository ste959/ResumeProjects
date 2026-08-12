"""Demo: the alpha-signal DSL, end to end.

Runs the full compiler pipeline on a handful of signals — tokens → AST → fingerprint → semantic
checks → evaluation — shows that the evaluator reproduces the hand-written factor code exactly, and
then runs a couple of one-line DSL signals through the real backtest engine.

Self-contained: uses a synthetic price/volume panel, so no data or network is needed.

    python run_dsl.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import alphadsl as dsl
from mds import engine as eng
from mds import factors as fc
from mds.dslstrategy import DslStrategy


def _panels(n=750, cols=("A", "B", "C", "D", "E", "F", "G", "H")):
    rng = np.random.default_rng(7)
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    steps = rng.normal(0.0002, 0.012, size=(n, len(cols)))
    close = pd.DataFrame(100 * np.exp(np.cumsum(steps, axis=0)), index=idx, columns=list(cols))
    volume = pd.DataFrame(rng.lognormal(12, 0.6, size=(n, len(cols))), index=idx, columns=list(cols))
    return close, volume


def section(title: str) -> None:
    print(f"\n{'─' * 78}\n{title}\n{'─' * 78}")


def main() -> None:
    close, volume = _panels()
    env = {"close": close, "volume": volume, "returns": close.pct_change()}

    section("1 · The language")
    print("operators:")
    for name, doc in dsl.operators().items():
        print(f"    {name:<10} {doc}")

    section("2 · Compile a signal (lex → parse → validate → fingerprint)")
    src = "rank(ts_delta(close, 5)) - 0.5 * zscore(log(volume))"
    sig = dsl.compile_signal(src, columns=set(env))
    print(f"source      : {src}")
    print(f"AST (pretty): {sig.ast.pretty()}")
    print(f"AST (canon) : {sig.ast.canonical()}")
    print(f"fingerprint : {sig.fingerprint}   columns used: {sorted(sig.columns)}")

    section("3 · Compile-time errors (caught before any data is touched)")
    for bad in ["ts_mean(close, -5)", "foo(close)", "zscore(close, 5)", "ts_mean(close, volume)"]:
        try:
            dsl.compile_signal(bad, columns=set(env))
        except dsl.ValidationError as e:
            print(f"    {bad:<26} →  {e}")

    section("4 · Correctness invariant: DSL evaluator == hand-written factors.py")
    a = dsl.evaluate("zscore(close)", env)
    b = fc._xs_zscore(close)
    print(f"    zscore(close) == factors._xs_zscore(close)              : "
          f"{np.allclose(a.values, b.values, equal_nan=True, atol=1e-12)}")
    a2 = dsl.evaluate("zscore(clip(zscore(close), -3, 3))", env)
    b2 = fc.standardize(close, winsor=3.0)
    print(f"    zscore(clip(zscore(close),-3,3)) == standardize(close)  : "
          f"{np.allclose(a2.values, b2.values, equal_nan=True, atol=1e-12)}")

    section("5 · One-line signals as strategies, through the real engine")
    signals = {
        "reversal_5d": "zscore(-ts_delta(close, 5))",
        "momentum_60d": "zscore(ts_delta(close, 60))",
        "lowvol": "-zscore(ts_std(returns, 20))",
        "blend": "zscore(-ts_delta(close, 5)) + 0.5 * -zscore(ts_std(returns, 20))",
    }
    cfg = eng.BacktestConfig(rebalance=5, cost_bps=5.0)
    print(f"    {'signal':<14}{'expression':<44}{'Sharpe':>8}{'turnover':>10}")
    for label, expr in signals.items():
        strat = DslStrategy(expr, list(close.columns), name=label, warmup=63,
                            extra_panels={"returns": env["returns"]})
        r = eng.run(strat, close, cfg)
        print(f"    {label:<14}{expr:<44}{r.stats['sharpe']:>8.2f}{r.turnover_ann:>10.1f}")

    print("\n(Synthetic data — the numbers are a plumbing demo, not an edge.)")


if __name__ == "__main__":
    main()
