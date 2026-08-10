"""Long-history daily data via yfinance — escaping the Alpaca IEX 2020 floor.

The free Alpaca IEX feed hard-caps history at 2020-07, so every study so far spanned one macro regime.
This layer pulls **20+ years** of split/dividend-adjusted daily bars from yfinance (free), reaching back
through the 2008 GFC, 2011, 2013, 2018 — the real stress regimes — and derives a risk-free rate from the
13-week T-bill (`^IRX`). Panels come out in the same shape as `alpaca_data.close_panel`, so every existing
study runs on the longer history unchanged.

Honest caveats (disclosed): yfinance is **survivorship-biased** (current tickers only) and its adjustments
aren't point-in-time perfect — but 20 years with disclosed survivorship beats 6 clean ones for statistical
power and regime coverage, and the point-in-time universe machinery is ready for better data. The pure
panel-extraction is unit-tested; only `fetch_panels` touches the network.
"""

from __future__ import annotations

import pathlib
import warnings

import pandas as pd

CACHE = pathlib.Path(__file__).resolve().parent.parent / "data" / "cache"
FIELDS = ("close", "high", "low", "volume")


def _extract_panels(df: pd.DataFrame, symbols: list[str], rf_symbol: str) -> tuple[dict, pd.Series]:
    """Turn a yfinance multi-index (field, ticker) frame into {field: symbols×dates panel} + a daily
    risk-free from the `rf_symbol` yield level (percent → daily). Network-free (testable)."""
    cap = {"close": "Close", "high": "High", "low": "Low", "volume": "Volume"}
    panels = {}
    for f, col in cap.items():
        wide = df[col] if isinstance(df.columns, pd.MultiIndex) else df[[col]].rename(columns={col: symbols[0]})
        panels[f] = wide.reindex(columns=symbols)
    rf_level = (df["Close"][rf_symbol] if isinstance(df.columns, pd.MultiIndex) else df["Close"])
    rf = (rf_level.astype(float) / 100.0 / 252.0).rename("rf")     # ^IRX is an annual % yield → daily rate
    return panels, rf


def fetch_panels(symbols: list[str], start: str = "2004-01-01", end: str = "2026-07-02",
                 rf_symbol: str = "^IRX", refresh: bool = False) -> tuple[dict, pd.Series]:
    """Fetch (or load cached) long-history OHLCV panels for `symbols` + a daily risk-free from `rf_symbol`.
    Cached to Parquet under data/cache/ (git-ignored)."""
    tag = "long_" + "_".join(symbols[:3]) + f"_{len(symbols)}"
    paths = {f: CACHE / f"{tag}_{f}.parquet" for f in FIELDS}
    rf_path = CACHE / f"{tag}_rf.parquet"
    if all(p.exists() for p in paths.values()) and rf_path.exists() and not refresh:
        panels = {f: pd.read_parquet(p) for f, p in paths.items()}
        rf = pd.read_parquet(rf_path)["rf"]
        return panels, rf

    import yfinance as yf
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = yf.download(symbols + [rf_symbol], start=start, end=end, auto_adjust=True, progress=False)
    panels, rf = _extract_panels(df, symbols, rf_symbol)
    CACHE.mkdir(parents=True, exist_ok=True)
    for f, p in paths.items():
        panels[f].to_parquet(p)
    rf.to_frame().to_parquet(rf_path)
    return panels, rf
