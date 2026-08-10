"""Data-quality auditing — trust the inputs before you trust the backtest.

Most "alpha" that evaporates in production was never alpha; it was a data artifact — an unadjusted split
read as a signal, a stale price that faked a smooth return, a gap that hid a loss. This module audits a
price/volume panel for the failures that silently corrupt a backtest, and returns a structured report so
a study can *gate* on clean data instead of assuming it.

Checks: coverage (missing history), calendar gaps, stale (repeated) prices, extreme jumps (likely
unadjusted corporate actions), non-positive prices, and duplicate timestamps. Pure NumPy/pandas — no I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def audit_prices(prices: pd.DataFrame, volume: pd.DataFrame | None = None,
                 stale_run: int = 5, jump_threshold: float = 0.40,
                 min_coverage: float = 0.90) -> dict:
    """Audit a symbols × dates price panel. Returns a per-symbol issue table plus a summary and a boolean
    `clean` flag. Thresholds: a `stale_run`+ run of identical closes, a one-day move beyond
    `jump_threshold` (a likely unadjusted split/dividend), and coverage below `min_coverage`."""
    issues: dict[str, dict] = {}
    rets = prices.pct_change()
    for sym in prices.columns:
        s = prices[sym]
        coverage = float(s.notna().mean())
        gaps = int(s.notna().astype(int).diff().eq(-1).sum())          # a present→absent transition = a gap
        # stale: longest run of identical consecutive (present) closes
        vals = s.dropna()
        stale = int((vals.diff().eq(0)).astype(int).groupby((vals.diff().ne(0)).cumsum()).sum().max() or 0)
        jumps = int((rets[sym].abs() > jump_threshold).sum())
        nonpos = int((s <= 0).sum())
        rec = {"coverage": round(coverage, 3), "gaps": gaps, "max_stale_run": stale,
               "extreme_jumps": jumps, "non_positive": nonpos,
               "flag": bool(coverage < min_coverage or stale >= stale_run or jumps > 0 or nonpos > 0)}
        issues[sym] = rec

    dup_dates = int(prices.index.duplicated().sum())
    flagged = [s for s, r in issues.items() if r["flag"]]
    summary = {
        "n_symbols": len(prices.columns),
        "n_flagged": len(flagged),
        "flagged": flagged,
        "duplicate_dates": dup_dates,
        "date_range": (str(prices.index.min().date()), str(prices.index.max().date())),
        "clean": bool(len(flagged) == 0 and dup_dates == 0),
    }
    return {"summary": summary, "by_symbol": issues}


def assert_clean(prices: pd.DataFrame, **kw) -> None:
    """Raise if the panel fails its data-quality audit — the gate to put in front of a real study."""
    report = audit_prices(prices, **kw)
    if not report["summary"]["clean"]:
        raise ValueError(f"data-quality audit failed: {report['summary']['n_flagged']} flagged symbols "
                         f"{report['summary']['flagged']}, {report['summary']['duplicate_dates']} dup dates")
