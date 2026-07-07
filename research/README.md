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
| `mds/statarb.py` | the **BTC/ETH stat-arb study** (cointegration diagnostic → walk-forward OOS z-score backtest → honest verdict) |
| `mds/lob.py`, `mds/models.py` | **microstructure ML** — leakage-free L2 feature/label harness + model zoo (ridge/GBM/MLP), walk-forward, purge/embargo, cost-aware |
| `mds/maker.py` | **maker-execution study** — passive fills, markout-based **adverse selection**, spread-vs-adverse decomposition (does a taker-dead signal survive as a maker?) |
| `mds/crosssec.py`, `mds/portfolio.py`, `mds/capacity.py` | **cross-sectional factors** (momentum/reversal/low-vol/BAB/idio-vol), beta+sector neutralization, a **walk-forward allocator**, and a **capacity/crowding** sizing model |
| `mds/validation.py` | **overfitting stats** — Newey–West Sharpe t-stat, block-bootstrap CI, **Deflated Sharpe**, **PBO** (CPCV), min-detectable-Sharpe power |
| `mds/edgar.py` | **SEC-EDGAR fundamentals** — point-in-time (filing-date) value/quality/accruals/investment factors |
| `mds/macro.py` | **FRED credit/VIX risk-off overlay** — a causal macro-timing score (halves the long-book drawdown) |
| `mds/options.py` | **Alpaca options surface** — live ATM-IV / 25Δ-skew / IV−RV cross-section |
| `mds/factors.py` | **multi-factor composite** — value/quality/momentum families → one standardized score (Grinold–Kahn: lift effective breadth) |
| `mds/riskmodel.py` | **factor risk model + constrained optimizer** — Σ=BFBᵀ+D and an analytic factor-neutral mean-variance solve with box + turnover caps |
| `mds/factortiming.py` | **regime-conditional factor timing** — rotate the family mix & time exposure on the FRED credit/VIX state, then vol-budget the book |
| `mds/structuring.py` | **options structuring overlay** — Black–Scholes tail hedge / covered-call / collar sized off the live IV surface |
| `mds/taxaware.py` | **tax-aware rebalancing** — tax-lot accounting, HIFO vs FIFO, wash sales, long/short holding periods (after-tax edge) |
| `service/` | **research bridge (FastAPI)** — exposes the layer to the front-end Research Lab: live backtests + the honest-null / construction snapshot (see [`service/README.md`](service/README.md)) |

The stat-arb study below is the entry point; the microstructure-ML, cross-sectional, portfolio,
capacity and **portfolio-construction** layers (Phases 5–7) are documented in
[`../MARKET-REALISM.md`](../MARKET-REALISM.md). The construction stack (`factors` → `riskmodel` →
`factortiming` → `structuring` → `taxaware`, driven by `run_construction.py`) is the QR's answer to
the null single-factor results: when standalone alpha is breadth-limited, *combining, risk-modelling,
timing, hedging and tax-managing* is where the medium-to-long-horizon value lives.
The technique is built and honest but the price-only data is exhausted (no significant edge) —
[`ALPHA-DATA-ROADMAP.md`](ALPHA-DATA-ROADMAP.md) is the QR plan for the data that would actually move
the needle (SEC-EDGAR fundamentals, macro/credit overlays, survivorship-free breadth, crypto L2).

## Run it

```bash
cd research
pip install -r requirements.txt         # pinned versions (numpy/pandas/sklearn/…)
python run_statarb.py           # fetches ~75 days of BTC/ETH, caches to Parquet, runs the study
python run_crosssec.py          # cross-sectional equity signals, with t-stats / 95% CIs
python run_fundamentals.py      # SEC-EDGAR value/quality/accruals factors (point-in-time)
python run_macro.py             # FRED credit/VIX risk-off overlay (halves the long-book drawdown)
python run_options.py           # live Alpaca options surface: ATM-IV / skew / IV−RV
python run_construction.py      # 5-layer portfolio construction: composite → risk model → timing → options → tax
python -m pytest                # 103 tests (offline; data modules fetch lazily)
```

## The philosophy: honest results beat pretty backtests

The study is built to *catch itself out*. It separates an **in-sample cointegration diagnostic**
(which only *describes* the window) from a **walk-forward out-of-sample backtest** (β re-fit on a
trailing window, traded on the next block). Example real output:

```
return correlation : 0.892      hedge ratio (beta) : 0.75
Engle-Granger ADF  : -1.88   (5% crit -3.34)   cointegrated @ 5% : False   [in-sample diagnostic]
OUT-OF-SAMPLE walk-forward:  net Sharpe -0.62   total return -1.94%   max drawdown -11.85%
VERDICT: No stable cointegration and no out-of-sample edge — the pairs assumption does not
hold over this window. An honest negative result.
```

The point: an in-sample z-score backtest on this pair shows a shiny **Sharpe 3.56** — which
**collapses to −0.62 out-of-sample** once the hedge ratio is estimated causally. The "edge" was
the leakage. Surfacing that — rather than reporting the 3.56 as "alpha" — is the whole point.
Throughout the layer, Sharpes are now reported **with t-stats and 95% confidence intervals**, so
a positive point estimate that isn't distinguishable from zero is named as such.
