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
    # A closed round-trip in the tag record (realized 20 with no fee), and the *real* position is flat.
    fills_by_strategy = {
        "btc-trend": {"BTC/USD": [
            {"side": "buy", "qty": 0.01, "price": 60000.0},
            {"side": "sell", "qty": 0.01, "price": 62000.0},   # realized 0.01*2000 = 20
        ]},
    }
    real_by_symbol = {"BTC/USD": {"qty": 0.0}}                  # real position flat
    rows = S.attribute(fills_by_strategy, real_by_symbol, marks={}, fee_rate=0.0)
    assert {r["id"] for r in rows} == set(S.REGISTRY)          # every strategy present, even empty
    btc = next(r for r in rows if r["id"] == "btc-trend")
    assert abs(btc["realized"] - 20.0) < 1e-6                  # realized from the tagged round-trip
    assert btc["unrealized"] == 0.0                            # real position flat → scaled to zero
    eth = next(r for r in rows if r["id"] == "eth-mom")
    assert eth["total_pnl"] == 0.0 and eth["n_fills"] == 0     # untouched strategy


def test_attribute_marks_reconciled_qty():
    # One strategy long 1 ETH; unrealized comes from the mark against the (fee-free) cost basis.
    fills_by_strategy = {"eth-mom": {"ETH/USD": [{"side": "buy", "qty": 1.0, "price": 3000.0}]}}
    real_by_symbol = {"ETH/USD": {"qty": 1.0}}
    rows = S.attribute(fills_by_strategy, real_by_symbol, marks={"ETH/USD": 3150.0}, fee_rate=0.0)
    eth = next(r for r in rows if r["id"] == "eth-mom")
    assert abs(eth["unrealized"] - 150.0) < 1e-6               # 1 * (3150 - 3000)
    assert abs(eth["gross_exposure"] - 3150.0) < 1e-6
    assert eth["positions"][0]["qty"] == 1.0


def test_fees_reduce_realized_pnl():
    # The same round-trip, now net of a 25 bps/side fee, must realize less than the fee-free 20.
    fills = [{"side": "buy", "qty": 0.01, "price": 60000.0},
             {"side": "sell", "qty": 0.01, "price": 62000.0}]
    gross = S.position_pnl(fills, None, fee_rate=0.0)["realized"]
    net = S.position_pnl(fills, None, fee_rate=0.0025)["realized"]
    assert abs(gross - 20.0) < 1e-6
    assert net < gross                                          # fees are actually charged
    # entry fee 0.01*60000*0.0025=1.5, exit fee 0.01*62000*0.0025=1.55 → ~16.95
    assert abs(net - (20.0 - 1.5 - 1.55)) < 1e-6


def test_attribute_splits_shared_symbol_no_double_count():
    # TWO strategies both long BTC. The single real position must be SPLIT, not handed to each.
    # (register a second BTC strategy for this test, then clean it up.)
    S.register("ma_crossover", "BTC/USD", "1Hour", {"fast": 20, "slow": 60})
    sid2 = "ma-btc-20-60"
    try:
        fills_by_strategy = {
            "btc-trend": {"BTC/USD": [{"side": "buy", "qty": 0.01, "price": 60000.0}]},
            sid2: {"BTC/USD": [{"side": "buy", "qty": 0.03, "price": 60000.0}]},
        }
        real_by_symbol = {"BTC/USD": {"qty": 0.04}}            # the real account holds the sum, once
        rows = S.attribute(fills_by_strategy, real_by_symbol, marks={"BTC/USD": 61000.0}, fee_rate=0.0)
        by_id = {r["id"]: r for r in rows}
        # unrealized splits 1:3 → total is the true 0.04*(61000-60000)=40, not double-counted to 80
        total_unreal = by_id["btc-trend"]["unrealized"] + by_id[sid2]["unrealized"]
        assert abs(total_unreal - 40.0) < 1e-6
        assert abs(by_id["btc-trend"]["unrealized"] - 10.0) < 1e-6   # 0.01/0.04 share
        assert abs(by_id[sid2]["unrealized"] - 30.0) < 1e-6          # 0.03/0.04 share
    finally:
        S.REGISTRY.pop(sid2, None)
