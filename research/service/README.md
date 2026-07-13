# `service/` — the Quant Desk service (FastAPI)

The Python backend for the front end's **Quant Desk** (`/research`) — an Alpaca-backed
**research → backtest → live** pipeline. It's the fourth service in the stack (alongside the OMS
backend, the risk microservice, and the frontend), reached single-origin via the `/research-api`
proxy (Vite in dev, nginx in prod). Endpoints live under `/api/research`.

Everything degrades gracefully: with no Alpaca keys it reports `configured: false` and the UI shows a
"connect Alpaca" state instead of erroring. The live strategy engine starts **disarmed** — nothing
trades until you explicitly arm a strategy.

## The three tabs it serves

- **Exploration** (`/market/*`) — screener (most-active / movers), server-computed **technicals**
  (Wilder RSI/ATR, SMAs, returns), **sector-ETF rotation**, live **news**, and a **catalyst** rail
  (FOMC schedule + trading calendar).
- **Backtest** (`/lab/*`) — a causal, cost-aware backtester (`/lab/backtest`) and an anchored
  **walk-forward out-of-sample** validator (`/lab/walkforward`) with the honest gauntlet (HAC t-stat,
  block-bootstrap CI, Bonferroni correction, power). `/lab/promote` registers a strategy **only if it
  clears the walk-forward server-side** — the gate is a real invariant, not a UI button.
- **Live Strategies** (`/status`, `/live/*`, `/strategies*`) — a background engine trading the paper
  account, with per-strategy P&L attribution and an automated risk layer (vol-targeted sizing,
  correlation-aware portfolio-vol cap, per-sleeve stops, latching drawdown auto-flatten, kill switch).

## Files

| File | Purpose |
|---|---|
| `app.py` | FastAPI app; mounts the desk router + the legacy research-lab routes. |
| `desk.py` | Quant Desk routes: `/status`, `/live/*`, `/strategies*`, `/lab/*`, `/market/*`. |
| `alpaca.py` | Thin, dependency-light Alpaca REST client (trading + market data + news) with retry/backoff. |
| `engine.py` | The live strategy engine — disarmed-by-default loop, tagged orders, risk limits, auto-flatten. |
| `strategies.py` | Pure strategy registry + signals + fee-aware P&L attribution (unit-tested, no I/O). |
| `lab.py` | Pure backtester + walk-forward OOS + the honest stat gauntlet. |
| `risk.py` | Pure portfolio risk math — annualized vol, covariance, vol-target notional, portfolio vol (√wᵀΣw). |
| `market.py` | Exploration data — technicals, screener, sectors, news, catalysts. |
| `compute.py` | Legacy Research-Lab compute over `../mds` (factor findings / construction snapshot). |
| `snapshot.json` | Baked told-story results for the legacy research-lab endpoints. |

The pure cores (`strategies`, `lab`, `risk`, `market` technicals) are tested without the web framework
or a live broker — the live money path is exercised through a **fake broker** in `../tests/test_engine.py`.

## Run it

```bash
cd research
pip install -r requirements.txt -r service/requirements.txt   # research deps + FastAPI/uvicorn/httpx
uvicorn service.app:app --port 8082                           # front end proxies /research-api → here
```

**Alpaca keys (optional):** set `ALPACA_API_KEY` / `ALPACA_API_SECRET` in the repo-root `.env`
(gitignored). Under `docker compose up` the service is built from `service/Dockerfile` with the Parquet
warehouse mounted read-only. Auth on order-control endpoints is opt-in — set `QD_API_TOKEN` to require
an `X-QD-Token` header. Offline tests: `python -m pytest`.
