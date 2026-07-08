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

# Assumed size of the parameter search behind each template — used to Bonferroni-correct the promote
# bar. Dragging the sliders IS a multiple-testing search; the winner must clear a bar raised for it.
SEARCH_TRIALS = {"ma_crossover": 40, "momentum": 15}

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


# The live crypto taker fee (per side). A backtest vetted below this can't honestly promote to live —
# "what you test is what trades" only holds if you test at the cost you'll pay.
LIVE_TAKER_BPS = S.CRYPTO_FEE_RATE * 1e4


def _bars_per_year(timeframe: str, is_crypto: bool) -> int:
    """252 trading days for daily equities; 365 for 24/7 crypto; hours/4-hours otherwise."""
    if timeframe == "1Day":
        return 365 if is_crypto else 252
    return BARS_PER_YEAR.get(timeframe, 252)


def _simulate(defn: S.StrategyDef, closes: list[float], timeframe: str, cost_bps: float) -> dict:
    """Causal, cost-aware backtest over a close-price series — the pure core, no I/O."""
    kind, symbol, params = defn.kind, defn.symbols[0], defn.params
    is_crypto = "/" in symbol
    ann = _bars_per_year(timeframe, is_crypto) ** 0.5

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

    ppy = _bars_per_year(timeframe, is_crypto)
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
    mdd = _max_drawdown(equity)
    avg_turn = turn_sum / n
    hit = (wins / active) if active else 0.0

    # Honest gauntlet: correct for the parameter SEARCH (you tried many combos → raise the bar), test
    # significance with an autocorrelation-preserving bootstrap CI, and flag an underpowered sample.
    trials = SEARCH_TRIALS.get(kind, 20)
    bar_t = float(val.bonferroni_z(trials))                        # ~2.9-3.1: the multiple-testing bar
    boot_lo, boot_hi = (float("nan"), float("nan"))
    if sd > 0 and n >= 8:
        boot_lo, boot_hi = val.block_bootstrap_sharpe_ci(net, ppy=ppy)   # annualized, autocorr-aware
    min_det = float(val.min_detectable_sharpe(n, ppy=ppy))         # smallest ann. Sharpe this N can see
    underpowered = sharpe < min_det
    significant = abs(hac_t) >= bar_t and boot_lo > 0
    # A candidate must also be vetted at (at least) the fee it will actually pay live.
    realistic_cost = cost_bps >= LIVE_TAKER_BPS
    passes = significant and sharpe > 0 and realistic_cost

    days = n / (ppy / 365.0)
    freq = {"1Hour": "hourly", "4Hour": "4-hour", "1Day": "daily"}.get(timeframe, timeframe)
    if passes:
        verdict = (f"Clears the search-corrected bar (|t| {abs(hac_t):.1f} > {bar_t:.1f} for ~{trials} tries) and the "
                   f"bootstrap Sharpe CI [{boot_lo:.1f}, {boot_hi:.1f}] excludes zero, at a realistic cost. A candidate — "
                   f"promote it and watch it forward; the backtest is in-sample, so live is the real out-of-sample test.")
    elif significant and sharpe > 0 and not realistic_cost:
        verdict = (f"Clears the significance bar, but you vetted it at {cost_bps:.0f} bps/side — below the ~{LIVE_TAKER_BPS:.0f} "
                   f"bps taker fee you'll actually pay live. Re-run at ≥{LIVE_TAKER_BPS:.0f} bps before promoting; a cheap-cost "
                   f"edge that dies at the real fee is not tradable.")
    elif underpowered and sharpe > 0:
        verdict = (f"Only {n} {freq} bars (~{days:.0f}d): this sample can't reliably detect an annualized Sharpe "
                   f"below ~{min_det:.1f}, and yours is {sharpe:.1f}. Underpowered — 'too little data to tell', not "
                   f"proven edge. Test on a longer window before trusting it.")
    elif sharpe > 0:
        verdict = (f"Sharpe {sharpe:.1f} ({freq}, annualized) but it fails the search-corrected bar — |t| {abs(hac_t):.1f} "
                   f"< {bar_t:.1f} and/or the bootstrap CI [{boot_lo:.1f}, {boot_hi:.1f}] includes zero. Given the param "
                   f"sweep, this is consistent with luck, not edge.")
    else:
        verdict = (f"Net Sharpe {sharpe:.1f} after {cost_bps:.0f} bps/side — a costed loser at {freq} frequency; the "
                   f"signal doesn't survive execution.")

    return {
        "ok": True, "kind": kind, "symbol": symbol, "timeframe": timeframe, "params": params,
        "cost_bps": cost_bps, "n_bars": n, "bars_per_year": ppy, "freq": freq, "window_days": round(days, 1),
        "net_sharpe": round(sharpe, 3), "hac_t": round(hac_t, 2), "bar_t": round(bar_t, 2), "trials": trials,
        "boot_lo": None if boot_lo != boot_lo else round(boot_lo, 2),
        "boot_hi": None if boot_hi != boot_hi else round(boot_hi, 2),
        "min_detectable": round(min_det, 2), "underpowered": bool(underpowered),
        "realistic_cost": bool(realistic_cost), "live_fee_bps": round(LIVE_TAKER_BPS, 1),
        "total_return": round(total_return, 4),
        "max_drawdown": round(mdd, 4), "avg_turnover": round(avg_turn, 4), "hit_rate": round(hit, 4),
        "passes": passes, "significant": significant, "equity_curve": _curve(equity), "verdict": verdict,
    }
