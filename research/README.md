# `research/` — quant research & backtesting over the live feed

A Python research layer that sits on top of the platform's live market data. It mirrors
how quant desks are actually organised: the **Java/Spring system** handles low-latency
trading (matching, execution, feed handling); this **Python layer** does research and
backtesting over a columnar data warehouse. Two languages, each for the job it's best at.

## Data architecture (capture → warehouse → research)

```
 Java MarketRecorder ──▶ append-only capture log (market-data/quotes-*.csv)
                                    │  DuckDB COPY (ETL)
 Coinbase candles API ──▶ Parquet cache ─┴─▶  Parquet warehouse  ──▶  DuckDB SQL  ──▶  pandas
```

- **Raw capture** is an append-only log (robust, cheap appends) — the idiomatic first hop.
- **Analytical store is columnar Parquet** (zstd-compressed, hive-partitioned by product),
  **queried with DuckDB** — the modern, server-less research-warehouse pattern. Historical
  candles are cached as Parquet so re-runs don't re-hit the exchange API.

## What's here

| Module | Purpose |
|---|---|
| `mds/sources.py`, `mds/store.py` | Coinbase candles + recorder capture → Parquet warehouse, DuckDB queries |
| `mds/stats.py` | **Hand-rolled econometrics** — OLS, ADF unit-root, **Engle–Granger cointegration**, **Ornstein–Uhlenbeck half-life** (no statsmodels) |
| `mds/features.py` | log returns, realized vol, order-book **imbalance → forward-return IC** |
| `mds/backtest.py` | vectorized backtester: transaction costs, **one-period execution lag (no look-ahead)**, Sharpe / drawdown / turnover / hit-rate |
| `mds/statarb.py` | the **BTC/ETH stat-arb study** (cointegration → z-score signal → cost-aware backtest → honest verdict) |

## Run it

```bash
cd research
pip install -r requirements.txt
python run_statarb.py           # fetches ~75 days of BTC/ETH, caches to Parquet, runs the study
python -m pytest                # 9 tests on synthetic data (no network)
```

## The philosophy: honest results beat pretty backtests

The study is built to *catch itself out*. Example real output:

```
return correlation : 0.892      hedge ratio (beta) : 0.75
Engle-Granger ADF  : -1.88   (5% crit -3.34)   cointegrated @ 5% : False
net Sharpe (ann.)  : 3.56    total return : 10.5%    max drawdown : -5.6%
VERDICT: RED FLAG: the in-sample Sharpe looks strong (3.56), but the pair is NOT
cointegrated at 5% — the mean-reversion premise fails, so this is almost certainly
spurious/overfit and would not survive out-of-sample. Do not trade it.
```

A shiny Sharpe with no cointegration is a **warning, not a win**. Surfacing that — rather
than reporting the 3.56 as "alpha" — is the whole point: rigorous methodology and
intellectual honesty about overfitting, costs, and out-of-sample risk.
