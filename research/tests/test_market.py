"""Tests for the pure technical indicators used by the Exploration tab."""

from __future__ import annotations

from service import market as M


def _bars(closes):
    # Minimal OHLC bars from a close series (flat intrabar range for simplicity).
    return [{"o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000} for c in closes]


def test_rsi_all_gains_is_100():
    up = list(range(1, 40))
    assert M._rsi(up, 14) == 100.0


def test_rsi_midrange_on_noise():
    closes = [100 + (5 if i % 2 else -5) for i in range(40)]   # alternating → RSI near 50
    r = M._rsi(closes, 14)
    assert r is not None and 30 < r < 70


def test_sma_and_returns():
    closes = [float(i) for i in range(1, 101)]                 # 1..100
    assert M._sma(closes, 10) == sum(range(91, 101)) / 10
    assert abs(M._ret(closes, 5) - (100 / 95 - 1)) < 1e-9


def test_atr_positive():
    bars = _bars([100 * (1.01 ** i) for i in range(30)])
    atr = M._atr(bars, 14)
    assert atr is not None and atr > 0


def test_compute_technicals_uptrend_flags_trend():
    bars = _bars([100 * (1.005 ** i) for i in range(120)])
    t = M.compute_technicals(bars)
    assert t["ok"] and t["trend"] is True                      # sma20 > sma50 in a steady rise
    assert t["rsi14"] is not None and t["ret_1m"] > 0
    assert len(t["spark"]) == 60


def test_compute_technicals_needs_history():
    assert M.compute_technicals(_bars([100.0])) == {"ok": False}
