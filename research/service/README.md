# `service/` — the research bridge (FastAPI)

A thin HTTP layer that exposes the Python research engine (`../mds`) to the BondDesk front end's
**Research Lab**. It is the fourth service in the stack, alongside the OMS backend, the risk
microservice, and the live feeds — the one that puts the quant-researcher persona on screen.

Two jobs, matching the Lab's two halves:

- **Live, interactive backtests.** `GET /api/research/backtest?signal=&cost_bps=&neutralize=` runs a
  dollar-neutral, walk-forward, cost-aware backtest of any signal (or the multi-factor `composite`)
  and returns the honest, overfitting-adjusted stats — Newey–West (HAC) t-stat, block-bootstrap 95%
  CI, the Bonferroni family bar — plus a downsampled equity curve. ~1s per run.
- **The told story, from a snapshot.** `GET /api/research/findings` and `/construction` serve a
  precomputed `snapshot.json`: the honest single-factor null (every factor's Sharpe + HAC t, the
  Deflated-Sharpe / PBO selection stats) and the five-layer construction stack (composite → risk
  model → timing → structuring → tax). The construction optimizer is ~45s, so it is baked, not run
  per request.

Everything reuses the exact `mds` modules the CLI drivers use, so the numbers the UI shows are the
same figures `run_crosssec.py` / `run_construction.py` print — not a re-derivation.

## Files
| File | Purpose |
|---|---|
| `compute.py` | Pure, JSON-returning functions over `mds` (testable without the web framework). |
| `app.py` | FastAPI routes under `/api/research`. |
| `export_snapshot.py` | Precompute `snapshot.json` (findings + construction). |
| `snapshot.json` | The baked told-story results (regenerate when data/modules change). |

## Run it
```bash
cd research
pip install -r requirements.txt -r service/requirements.txt   # research deps + FastAPI/uvicorn
python -m service.export_snapshot                             # (re)build snapshot.json  (~1 min)
uvicorn service.app:app --port 8082                           # serve; front end proxies /research → here
```
The front end reaches it single-origin via the `/research` proxy (Vite in dev, nginx in prod);
`docker compose up` builds it from `service/Dockerfile` with the Parquet warehouse mounted read-only
so live backtests work. Offline tests: `python -m pytest tests/test_service.py`.
