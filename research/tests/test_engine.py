"""Tests for the live engine's money path with a fake broker — the code that actually submits orders.

Covers the behaviors the perspective review flagged as untested: hysteresis (enter/hold/exit), the
kill switch halting mid-cycle, the kill latch (arm does not release it), the pending-order guard, and
that a disarmed engine trades nothing.
"""

from __future__ import annotations

import sys
import types

# The engine imports `alpaca`, which imports httpx (not needed for these tests). Shim it so the module
# imports cleanly; we monkeypatch the broker functions anyway.
if "httpx" not in sys.modules:
    _fake = types.ModuleType("httpx")
    _fake.Client = type("Client", (), {"__init__": lambda self, *a, **k: None})
    _fake.HTTPError = type("HTTPError", (Exception,), {})
    sys.modules["httpx"] = _fake

import pytest  # noqa: E402

from service import engine  # noqa: E402
from service import strategies as S  # noqa: E402

RISING = [100 * (1.001 ** i) for i in range(120)]    # btc-trend (fast12/slow48) → target_sign == 1
FALLING = [100 * (0.999 ** i) for i in range(120)]   # → target_sign == 0


@pytest.fixture
def broker(monkeypatch):
    """A fake Alpaca: records submitted orders; sign/positions/pending are configurable per test."""
    state = {"closes": RISING, "positions": [], "open": [], "submitted": []}

    def submit(sym, qty, side, **kw):
        state["submitted"].append({"symbol": sym, "side": side, "qty": qty, "coid": kw.get("client_order_id")})
        return {"id": "x"}

    monkeypatch.setattr(engine.alpaca, "configured", lambda: True)
    monkeypatch.setattr(engine.alpaca, "crypto_closes", lambda sym, **k: state["closes"])
    monkeypatch.setattr(engine.alpaca, "crypto_marks", lambda syms: {s: 100.0 for s in syms})
    monkeypatch.setattr(engine.alpaca, "positions", lambda: state["positions"])
    monkeypatch.setattr(engine.alpaca, "all_orders", lambda **k: [])
    monkeypatch.setattr(engine.alpaca, "orders", lambda **k: state["open"])
    monkeypatch.setattr(engine.alpaca, "submit_order", submit)

    engine._STATE["armed"].clear()
    engine._STATE["kill"] = False
    engine._STATE["actions"].clear()
    engine._STATE["books"] = []
    engine._STATE["pnl_peak"] = None
    engine._STATE["risk_halt"] = False
    yield state
    engine._STATE["armed"].clear()
    engine._STATE["kill"] = False
    engine._STATE["books"] = []
    engine._STATE["pnl_peak"] = None
    engine._STATE["risk_halt"] = False


def _pos(sym, qty):
    return {"symbol": engine.alpaca.position_symbol(sym), "qty": str(qty), "qty_available": str(qty),
            "avg_entry_price": "100", "unrealized_pl": "0", "market_value": str(qty * 100)}


def test_disarmed_trades_nothing(broker):
    broker["closes"] = RISING
    engine.run_once()
    assert broker["submitted"] == []


def test_enter_on_flip_to_long(broker):
    broker["closes"] = RISING            # signal long
    broker["positions"] = []             # flat
    engine._STATE["armed"].add("btc-trend")
    engine._trade_armed({"BTC/USD": {"qty": 0.0, "qty_available": "0"}}, {"BTC/USD": 100.0})
    assert len(broker["submitted"]) == 1
    assert broker["submitted"][0]["side"] == "buy"


def test_hold_while_long_no_rebalance(broker):
    broker["closes"] = RISING            # still long
    engine._STATE["armed"].add("btc-trend")
    # already holding a meaningful position → hysteresis says HOLD, no order (the constant-dollar bug)
    engine._trade_armed({"BTC/USD": {"qty": 15.0, "qty_available": "15"}}, {"BTC/USD": 100.0})
    assert broker["submitted"] == []


def test_exit_on_flip_to_flat(broker):
    broker["closes"] = FALLING           # signal flat
    engine._STATE["armed"].add("btc-trend")
    engine._trade_armed({"BTC/USD": {"qty": 15.0, "qty_available": "15"}}, {"BTC/USD": 100.0})
    assert len(broker["submitted"]) == 1
    assert broker["submitted"][0]["side"] == "sell"


def test_kill_halts_mid_cycle(broker):
    broker["closes"] = RISING
    # Simulate kill pressed during the cycle: killed True but armed still populated.
    engine._STATE["armed"].add("btc-trend")
    engine._STATE["kill"] = True
    engine._trade_armed({"BTC/USD": {"qty": 0.0, "qty_available": "0"}}, {"BTC/USD": 100.0})
    assert broker["submitted"] == []     # _halted guard stops it before any order


def test_pending_order_blocks_new_order(broker):
    broker["closes"] = RISING
    broker["open"] = [{"client_order_id": "qd-btc-trend-1", "symbol": "BTC/USD"}]  # a working order
    engine._STATE["armed"].add("btc-trend")
    engine._trade_armed({"BTC/USD": {"qty": 0.0, "qty_available": "0"}}, {"BTC/USD": 100.0})
    assert broker["submitted"] == []     # don't stack on an open order


def test_kill_is_a_latch_arm_does_not_release(broker):
    engine.kill()
    assert engine._STATE["kill"] is True and engine._STATE["armed"] == set()
    engine.arm("btc-trend")              # arming must NOT clear the kill
    assert engine._STATE["kill"] is True
    assert "btc-trend" in engine._STATE["armed"]
    engine.resume()                      # only resume clears it
    assert engine._STATE["kill"] is False


def test_run_once_skips_trading_while_killed(broker):
    broker["closes"] = RISING
    engine._STATE["armed"].add("btc-trend")
    engine._STATE["kill"] = True
    engine.run_once()                    # refresh runs, but trading is skipped
    assert broker["submitted"] == []


def test_gross_cap_blocks_new_entry(broker):
    broker["closes"] = RISING            # btc-trend wants to go long BTC
    engine._STATE["armed"].add("btc-trend")
    # BTC is flat for this sleeve, but ETH already holds $7,000 → entering $1,500 more would breach $8,000
    real = {"ETH/USD": {"qty": 70.0, "qty_available": "70"}}
    engine._trade_armed(real, {"BTC/USD": 100.0, "ETH/USD": 100.0})
    assert broker["submitted"] == []     # gross cap blocked the entry
    assert any(a["kind"] == "risk" for a in engine._STATE["actions"])


def test_session_drawdown_auto_flattens_and_kills(broker):
    broker["positions"] = [_pos("BTC/USD", 15)]      # a real position to close
    engine._STATE["armed"].add("btc-trend")
    engine._STATE["books"] = [{"gross_exposure": 1500.0, "total_pnl": -800.0}]  # dropped below the -750 limit
    engine._STATE["pnl_peak"] = 0.0
    halted = engine._risk_check()
    assert halted is True
    assert engine._STATE["kill"] is True             # latched off
    assert any(o["side"] == "sell" for o in broker["submitted"])   # auto-flattened the position
