"""mds — a small market-data-science toolkit for the BondDesk live feed.

Layers: `sources`/`store` (Coinbase candles + recorder capture, warehoused as Parquet
and queried with DuckDB), `stats` (hand-rolled OLS / ADF / Engle–Granger / OU half-life),
`features` (returns, vol, microstructure), `backtest` (costs + metrics), and `statarb`
(the BTC/ETH pairs study).
"""

from . import backtest, features, sources, statarb, stats, store  # noqa: F401

__all__ = ["backtest", "features", "sources", "statarb", "stats", "store"]
