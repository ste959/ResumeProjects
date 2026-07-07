"""Research service — a thin FastAPI wrapper over `compute.py`.

Exposes the research layer to the front end so the Research Lab can (a) tell the honest-null /
construction story from a precomputed snapshot, and (b) run *live* single-signal backtests with
reviewer-chosen parameters. Mirrors the risk-service pattern: paths live under `/api/research`, and
the front end reaches them single-origin via the `/research` proxy (Vite in dev, nginx in prod).

Run locally:   uvicorn service.app:app --port 8082   (from the research/ directory)
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import compute
from .desk import router as desk_router

app = FastAPI(title="BondDesk Research Service", version="1.0.0",
              summary="Live backtests + the honest-null / construction snapshot for the Research Lab.")

# The fresh Quant Desk surface (Alpaca-backed research → backtest → live).
app.include_router(desk_router)

# Same localhost-friendly CORS as the OMS backend (direct access in dev; the proxy is same-origin).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=os.environ.get("RESEARCH_CORS_REGEX", r"http://localhost:\d+"),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/research/health")
def health() -> dict:
    """Liveness + whether the told-story snapshot is present (vs. computed on demand)."""
    return {"status": "UP", "snapshot": compute.SNAPSHOT_PATH.exists(),
            "signals": len(compute.list_signals())}


@app.get("/api/research/signals")
def signals() -> list[dict]:
    """The signal menu for the interactive control."""
    return compute.list_signals()


@app.get("/api/research/backtest")
def backtest(signal: str = Query(..., description="signal name or 'composite'"),
             cost_bps: float = Query(5.0, ge=0.0, le=100.0),
             neutralize: bool = Query(True)) -> dict:
    """Live single-signal backtest with honest stats + a downsampled equity curve."""
    try:
        return compute.backtest_signal(signal, cost_bps=cost_bps, neutralize=neutralize)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown signal: {signal}")


@app.get("/api/research/microstructure")
def microstructure(ic: float = Query(0.10, ge=0.0, le=0.30, description="ground-truth 1-step OFI IC"),
                   signal: str = Query("ofi", description="ofi | ofi_smooth | queue_imb")) -> dict:
    """Microstructure alpha: a known-IC order-flow tape, the signal-decay curve, and the cost sweep
    that finds the break-even between a predictive signal and a tradable one."""
    try:
        return compute.microstructure_study(ic=ic, signal=signal)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown signal: {signal}")


@app.get("/api/research/findings")
def findings() -> dict:
    """The 'honest null' single-factor table + selection-aware stats (snapshot, else computed)."""
    snap = compute.load_snapshot()
    if snap and "findings" in snap:
        return snap["findings"]
    return compute.compute_findings()


@app.get("/api/research/construction")
def construction() -> dict:
    """The five-layer construction stack (snapshot preferred — the optimizer is ~45s to recompute)."""
    snap = compute.load_snapshot()
    if snap and "construction" in snap:
        return snap["construction"]
    return compute.compute_construction()
