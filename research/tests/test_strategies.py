"""Tests for the pure strategy + attribution core — signals, order tagging, and the average-cost P&L
that turns tagged fills into per-strategy realized/unrealized numbers."""

from __future__ import annotations

from service import strategies as S


def test_order_tag_roundtrips_to_strategy():
    tag = S.order_tag("btc-trend", 7)
    assert tag == "qd-btc-trend-7"
    assert S.strategy_of(tag) == "btc-trend"
    assert S.strategy_of("qd-eth-mom-0") == "eth-mom"
    assert S.strategy_of(None) is None
    assert S.strategy_of("hand-placed-123") is None      # untagged / manual order
    assert S.strategy_of("qd-unknown-1") is None          # not in the registry


def test_ma_crossover_signal():
    defn = S.REGISTRY["btc-trend"]
    up = list(range(1, 200))                               # steadily rising → fast > slow → long
    assert S.target_sign(defn, up) == 1
    down = list(range(200, 1, -1))                         # falling → fast < slow → flat
    assert S.target_sign(defn, down) == 0
    assert S.target_sign(defn, [1, 2, 3]) == 0             # not enough history → flat


def test_momentum_signal_and_qty():
    defn = S.REGISTRY["eth-mom"]
    closes = [100.0] * 30 + [130.0]                        # positive trailing return → long
    assert S.target_sign(defn, closes) == 1
    q = S.target_qty(defn, closes)
    assert abs(q - defn.notional / 130.0) < 1e-6           # notional / price units
    flat = [100.0] * 30 + [90.0]                           # negative → flat, 0 size
    assert S.target_qty(defn, flat) == 0.0


def test_position_pnl_average_cost():
    fills = [
        {"side": "buy", "qty": 10, "price": 100.0},
        {"side": "buy", "qty": 10, "price": 110.0},        # avg cost → 105 on 20
        {"side": "sell", "qty": 5, "price": 120.0},        # realize 5*(120-105)=75, 15 left @105
    ]
    pnl = S.position_pnl(fills, mark=130.0)
    assert pnl["qty"] == 15
    assert abs(pnl["avg_cost"] - 105.0) < 1e-9
    assert abs(pnl["realized"] - 75.0) < 1e-9
    assert abs(pnl["unrealized"] - 15 * (130.0 - 105.0)) < 1e-9   # 375


def test_position_pnl_full_close_flat():
    fills = [
        {"side": "buy", "qty": 4, "price": 50.0},
        {"side": "sell", "qty": 4, "price": 60.0},         # closed: realize 4*10 = 40, flat
    ]
    pnl = S.position_pnl(fills, mark=70.0)
    assert pnl["qty"] == 0
    assert abs(pnl["realized"] - 40.0) < 1e-9
    assert pnl["unrealized"] == 0.0                        # no open position → no mark risk


def test_attribute_realized_from_fills_holdings_from_reality():
    # A closed round-trip in the tag record (realized 20), and the *real* position is flat.
    fills_by_strategy = {
        "btc-trend": {"BTC/USD": [
            {"side": "buy", "qty": 0.01, "price": 60000.0},
            {"side": "sell", "qty": 0.01, "price": 62000.0},   # realized 0.01*2000 = 20
        ]},
    }
    real_by_symbol = {"BTC/USD": {"qty": 0.0, "avg_cost": 0.0, "unrealized": 0.0, "market_value": 0.0}}
    rows = S.attribute(fills_by_strategy, real_by_symbol)
    assert {r["id"] for r in rows} == set(S.REGISTRY)          # every strategy present, even empty
    btc = next(r for r in rows if r["id"] == "btc-trend")
    assert abs(btc["realized"] - 20.0) < 1e-6                  # realized from the tagged round-trip
    assert btc["unrealized"] == 0.0                            # real position is flat → no unrealized
    eth = next(r for r in rows if r["id"] == "eth-mom")
    assert eth["total_pnl"] == 0.0 and eth["n_fills"] == 0     # untouched strategy


def test_attribute_uses_live_unrealized_from_real_position():
    # An open real position drives live unrealized/market value (fee-exact ground truth).
    fills_by_strategy = {"eth-mom": {"ETH/USD": [{"side": "buy", "qty": 1.0, "price": 3000.0}]}}
    real_by_symbol = {"ETH/USD": {"qty": 1.0, "avg_cost": 3000.0, "unrealized": 150.0, "market_value": 3150.0}}
    rows = S.attribute(fills_by_strategy, real_by_symbol)
    eth = next(r for r in rows if r["id"] == "eth-mom")
    assert eth["unrealized"] == 150.0
    assert abs(eth["gross_exposure"] - 3150.0) < 1e-6
    assert eth["positions"][0]["qty"] == 1.0
