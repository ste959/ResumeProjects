"""The backtest lab — parameterized, cost-aware backtests over real Alpaca history.

The point of the whole pipeline: a signal is vetted here before it trades real (paper) money. Crucially
the backtest runs the *same* `strategies.target_sign` the live engine uses, so what you test is exactly
what trades — no backtest/live drift. Everything is causal (the position for bar t→t+1 is decided from
data through t only) and net of a round-trip cost charged on every position change. A survivor can be
promoted straight into the live registry.
"""

from __future__ import annotations

import pathlib
import sys

# research/ on the path so `from mds import validation` works regardless of the working directory.
_RESEARCH_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_ROOT))

from mds import validation as val   # noqa: E402

from . import strategies as S       # noqa: E402

# Bars per year for annualising the Sharpe, and how many bars to pull per timeframe.
BARS_PER_YEAR = {"1Hour": 24 * 365, "4Hour": 6 * 365, "1Day": 365}
FETCH_LIMIT = {"1Hour": 720, "4Hour": 540, "1Day": 365}

# The strategy templates the lab exposes — each maps to a live signal in strategies.py. `code` is the
# exact logic (params interpolated) shown to the user; the controls edit params, never free-text code.
TEMPLATES = [
    {
        "kind": "ma_crossover", "name": "MA Crossover",
        "desc": "Go long when the fast moving average crosses above the slow one; flat otherwise.",
        "params": [
            {"key": "fast", "label": "Fast MA (bars)", "min": 3, "max": 60, "default": 12},
            {"key": "slow", "label": "Slow MA (bars)", "min": 10, "max": 200, "default": 48},
        ],
        "code": "fast_ma = sma(close, {fast})\nslow_ma = sma(close, {slow})\nposition = 1 if fast_ma > slow_ma else 0",
    },
    {
        "kind": "momentum", "name": "Time-Series Momentum",
        "desc": "Go long when the trailing return over the lookback is positive; flat when it rolls over.",
        "params": [
            {"key": "lookback", "label": "Lookback (bars)", "min": 4, "max": 120, "default": 24},
        ],
        "code": "trailing_ret = close / close[-{lookback}] - 1\nposition = 1 if trailing_ret > 0 else 0",
    },
]
TEMPLATE_BY_KIND = {t["kind"]: t for t in TEMPLATES}

# The universe the lab can test. Crypto is promotable to live (24/7, matches the engine); equities are
# evaluate-only for now (market hours + separate order path).
UNIVERSE = [
    {"symbol": "BTC/USD", "label": "Bitcoin", "asset_class": "crypto", "promotable": True},
    {"symbol": "ETH/USD", "label": "Ethereum", "asset_class": "crypto", "promotable": True},
    {"symbol": "LTC/USD", "label": "Litecoin", "asset_class": "crypto", "promotable": True},
    {"symbol": "AAPL", "label": "Apple", "asset_class": "us_equity", "promotable": False},
    {"symbol": "SPY", "label": "S&P 500 ETF", "asset_class": "us_equity", "promotable": False},
]


def _bars(symbol: str, timeframe: str) -> list[float]:
    from . import alpaca  # lazy — keeps the pure `_simulate` importable without httpx
    limit = FETCH_LIMIT.get(timeframe, 500)
    if "/" in symbol:
        data = alpaca.crypto_bars([symbol], timeframe=timeframe, limit=limit)
    else:
        data = alpaca.stock_bars(symbol, timeframe=timeframe, limit=limit)
    bars = (data.get("bars") or {}).get(symbol) or []
    return [float(b["c"]) for b in bars if b.get("c") is not None]


def _curve(equity: list[float], points: int = 180) -> list[dict]:
    if not equity:
        return []
    step = max(1, len(equity) // points)
    idx = list(range(0, len(equity), step))
    if idx[-1] != len(equity) - 1:
        idx.append(len(equity) - 1)
    return [{"i": i, "value": round(equity[i], 5)} for i in idx]


def _max_drawdown(equity: list[float]) -> float:
    peak, mdd = equity[0] if equity else 1.0, 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return mdd


def backtest(kind: str, symbol: str, timeframe: str, params: dict, cost_bps: float,
             notional: float = 1000.0) -> dict:
    """Fetch history and run the backtest. Thin wrapper over the pure `_simulate` (which the tests hit)."""
    if kind not in TEMPLATE_BY_KIND:
        raise KeyError(kind)
    closes = _bars(symbol, timeframe)
    defn = S.StrategyDef(id="bt", name="backtest", desc="", kind=kind,
                         asset_class="crypto" if "/" in symbol else "us_equity",
                         symbols=(symbol,), params=params, notional=notional)
    return _simulate(defn, closes, timeframe, cost_bps)


def _simulate(defn: S.StrategyDef, closes: list[float], timeframe: str, cost_bps: float) -> dict:
    """Causal, cost-aware backtest over a close-price series — the pure core, no I/O."""
    kind, symbol, params = defn.kind, defn.symbols[0], defn.params
    ann = (BARS_PER_YEAR.get(timeframe, 252)) ** 0.5

    net, pos_prev, turn_sum, active, wins = [], 0.0, 0.0, 0, 0
    for t in range(len(closes) - 1):
        sign = float(S.target_sign(defn, closes[:t + 1]))     # causal: decided from data through t
        r = closes[t + 1] / closes[t] - 1.0
        gross = sign * r
        turn = abs(sign - pos_prev)
        net_t = gross - turn * (cost_bps / 1e4)
        net.append(net_t)
        turn_sum += turn
        pos_prev = sign
        if sign != 0:
            active += 1
            if gross > 0:
                wins += 1

    n = len(net)
    if n < 5:
        return {"ok": False, "reason": "not enough history for this symbol/timeframe.",
                "symbol": symbol, "timeframe": timeframe, "n_bars": n}

    mean = sum(net) / n
    var = sum((x - mean) ** 2 for x in net) / n
    sd = var ** 0.5
    sharpe = (mean / sd * ann) if sd > 0 else 0.0
    hac_t = float(val.newey_west_sharpe_tstat(net)) if sd > 0 else 0.0

    equity, e = [], 1.0
    for x in net:
        e *= (1.0 + x)
        equity.append(e)
    total_return = equity[-1] - 1.0
    ann_return = (equity[-1] ** (BARS_PER_YEAR.get(timeframe, 252) / n)) - 1.0 if equity[-1] > 0 else -1.0
    mdd = _max_drawdown(equity)
    avg_turn = turn_sum / n
    hit = (wins / active) if active else 0.0
    passes = abs(hac_t) >= 2.0 and sharpe > 0

    if passes:
        verdict = (f"Net Sharpe {sharpe:.2f} (HAC t {hac_t:+.1f}) over {n} bars — clears the |t|>2 bar with a "
                   f"positive edge. A candidate: promote it to a live paper sleeve and watch it out-of-sample. "
                   f"A backtest edge is necessary, not sufficient.")
    elif sharpe > 0:
        verdict = (f"Net Sharpe {sharpe:.2f} but HAC t is only {hac_t:+.1f} (< 2) — not distinguishable from "
                   f"luck once autocorrelation is accounted for. Not yet a candidate.")
    else:
        verdict = (f"Net Sharpe {sharpe:.2f} after {cost_bps:.0f} bps cost — a costed loser. The signal doesn't "
                   f"survive execution at this frequency.")

    return {
        "ok": True, "kind": kind, "symbol": symbol, "timeframe": timeframe, "params": params,
        "cost_bps": cost_bps, "n_bars": n,
        "net_sharpe": round(sharpe, 3), "hac_t": round(hac_t, 2),
        "total_return": round(total_return, 4), "ann_return": round(ann_return, 4),
        "max_drawdown": round(mdd, 4), "avg_turnover": round(avg_turn, 4), "hit_rate": round(hit, 4),
        "passes": passes, "equity_curve": _curve(equity), "verdict": verdict,
    }
