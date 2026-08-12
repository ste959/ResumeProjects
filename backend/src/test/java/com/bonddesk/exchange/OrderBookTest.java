package com.bonddesk.exchange;

import org.junit.jupiter.api.Test;

import static com.bonddesk.exchange.OrderType.LIMIT;
import static com.bonddesk.exchange.OrderType.MARKET;
import static com.bonddesk.exchange.Side.BUY;
import static com.bonddesk.exchange.Side.SELL;
import static com.bonddesk.exchange.TimeInForce.FOK;
import static com.bonddesk.exchange.TimeInForce.GTC;
import static com.bonddesk.exchange.TimeInForce.IOC;
import static org.assertj.core.api.Assertions.assertThat;

/** Correctness of the matching engine — the invariants a real exchange must hold. */
class OrderBookTest {

    private OrderBook book() {
        return new OrderBook("BTC-USD");
    }

    private SubmitResult limit(OrderBook b, String who, Side side, long px, long qty, TimeInForce tif) {
        return b.submit(who, side, LIMIT, tif, false, px, qty);
    }

    @Test
    void restsWhenItDoesNotCross() {
        OrderBook b = book();
        SubmitResult r = limit(b, "A", BUY, 100, 5, GTC);
        assertThat(r.status()).isEqualTo(SubmitResult.Status.RESTING);
        assertThat(r.trades()).isEmpty();
        assertThat(b.bestBid()).isEqualTo(100);
        assertThat(b.restingQuantity()).isEqualTo(5);
    }

    @Test
    void aggressorTradesAtRestingMakerPrice() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 5, GTC);
        SubmitResult r = limit(b, "B", BUY, 101, 5, GTC); // willing to pay 101, but fills at maker's 100
        assertThat(r.status()).isEqualTo(SubmitResult.Status.FILLED);
        assertThat(r.trades()).hasSize(1);
        assertThat(r.trades().get(0).priceTicks()).isEqualTo(100);
        assertThat(r.trades().get(0).makerParticipant()).isEqualTo("A");
        assertThat(r.trades().get(0).takerParticipant()).isEqualTo("B");
        assertThat(b.restingQuantity()).isZero();
    }

    @Test
    void bestPriceMatchesFirst() {
        OrderBook b = book();
        limit(b, "A", SELL, 101, 5, GTC);
        limit(b, "B", SELL, 100, 5, GTC);
        SubmitResult r = b.submit("C", BUY, MARKET, IOC, false, 0, 5);
        assertThat(r.trades()).hasSize(1);
        assertThat(r.trades().get(0).priceTicks()).isEqualTo(100); // took the better (lower) ask
        assertThat(r.trades().get(0).makerParticipant()).isEqualTo("B");
    }

    @Test
    void timePriorityIsFifoWithinAPriceLevel() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 5, GTC); // rested first
        limit(b, "B", SELL, 100, 5, GTC); // rested second
        SubmitResult r = b.submit("C", BUY, MARKET, IOC, false, 0, 5);
        assertThat(r.trades().get(0).makerParticipant()).isEqualTo("A"); // earliest fills first
    }

    @Test
    void partialFillRestsTheRemainder() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 5, GTC);
        SubmitResult r = limit(b, "B", BUY, 100, 8, GTC);
        assertThat(r.status()).isEqualTo(SubmitResult.Status.RESTING);
        assertThat(r.filledQty()).isEqualTo(5);
        assertThat(r.restingQty()).isEqualTo(3);
        assertThat(b.bestBid()).isEqualTo(100);
        assertThat(b.bestAsk()).isNull();
    }

    @Test
    void marketOrderNeverRests() {
        OrderBook b = book();
        SubmitResult r = b.submit("A", BUY, MARKET, IOC, false, 0, 5); // empty book
        assertThat(r.status()).isEqualTo(SubmitResult.Status.CANCELLED);
        assertThat(b.restingQuantity()).isZero();
    }

    @Test
    void iocCancelsTheUnfilledRemainder() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 3, GTC);
        SubmitResult r = limit(b, "B", BUY, 100, 5, IOC);
        assertThat(r.status()).isEqualTo(SubmitResult.Status.PARTIALLY_FILLED);
        assertThat(r.filledQty()).isEqualTo(3);
        assertThat(r.restingQty()).isZero();
        assertThat(b.bestBid()).isNull(); // nothing rested
    }

    @Test
    void fokRejectsWhenNotFullyFillableAndPrintsNothing() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 3, GTC);
        SubmitResult r = limit(b, "B", BUY, 100, 5, FOK); // only 3 available
        assertThat(r.status()).isEqualTo(SubmitResult.Status.REJECTED);
        assertThat(r.trades()).isEmpty();
        assertThat(b.restingQuantity()).isEqualTo(3); // the resting sell is untouched
    }

    @Test
    void fokFillsWhenFullyFillable() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 5, GTC);
        SubmitResult r = limit(b, "B", BUY, 100, 5, FOK);
        assertThat(r.status()).isEqualTo(SubmitResult.Status.FILLED);
        assertThat(r.filledQty()).isEqualTo(5);
    }

    @Test
    void fokDoesNotCountOwnLiquiditySelfTradePreventionWillCancel() {
        // Regression: FOK all-or-nothing must hold even when the aggressor's *own* resting orders
        // sit in the crossable liquidity. STP cancels those instead of trading them, so counting
        // them in the fillability check would let a FOK order pass the gate and then partial-fill.
        OrderBook b = book();
        limit(b, "A", SELL, 100, 3, GTC);              // A's own resting size — STP will cancel it
        limit(b, "B", SELL, 100, 2, GTC);              // only 2 are genuinely tradable for A
        SubmitResult r = limit(b, "A", BUY, 100, 5, FOK); // needs 5; only 2 tradable
        assertThat(r.status()).isEqualTo(SubmitResult.Status.REJECTED); // all-or-nothing upheld
        assertThat(r.trades()).isEmpty();              // no partial print escaped
        assertThat(b.tradeCount()).isZero();
        assertThat(b.restingQuantity()).isEqualTo(5);  // both resting sells untouched
    }

    @Test
    void fokFillsAgainstOthersLiquidityIgnoringOwnRestingSize() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 3, GTC);              // A's own — cancelled by STP during the sweep
        limit(b, "B", SELL, 100, 5, GTC);              // 5 tradable for A → FOK is satisfiable
        SubmitResult r = limit(b, "A", BUY, 100, 5, FOK);
        assertThat(r.status()).isEqualTo(SubmitResult.Status.FILLED);
        assertThat(r.filledQty()).isEqualTo(5);
        assertThat(b.tradeCount()).isEqualTo(1);       // one real trade against B
        assertThat(b.restingQuantity()).isZero();      // B's 5 traded, A's 3 STP-cancelled
    }

    @Test
    void postOnlyRejectsIfItWouldCross() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 5, GTC);
        SubmitResult r = b.submit("B", BUY, LIMIT, GTC, true, 100, 5); // would take → reject
        assertThat(r.status()).isEqualTo(SubmitResult.Status.REJECTED);
        assertThat(r.reason()).contains("post-only");
    }

    @Test
    void postOnlyRestsWhenItDoesNotCross() {
        OrderBook b = book();
        SubmitResult r = b.submit("A", BUY, LIMIT, GTC, true, 100, 5);
        assertThat(r.status()).isEqualTo(SubmitResult.Status.RESTING);
    }

    @Test
    void selfTradePreventionCancelsMakerInsteadOfWashing() {
        OrderBook b = book();
        limit(b, "A", SELL, 100, 5, GTC);
        SubmitResult r = limit(b, "A", BUY, 100, 5, GTC); // same participant crosses its own quote
        assertThat(r.trades()).isEmpty();          // no wash trade
        assertThat(b.tradeCount()).isZero();
        assertThat(b.bestAsk()).isNull();          // the resting sell was cancelled by STP
        assertThat(b.bestBid()).isEqualTo(100);    // the aggressor rested (nothing left to hit)
    }

    @Test
    void cancelRemovesRestingOrder() {
        OrderBook b = book();
        SubmitResult r = limit(b, "A", BUY, 100, 5, GTC);
        assertThat(b.cancel(r.orderId())).isTrue();
        assertThat(b.bestBid()).isNull();
        assertThat(b.cancel(r.orderId())).isFalse(); // already gone
    }

    @Test
    void replaceReductionKeepsTimePriority() {
        OrderBook b = book();
        SubmitResult a = limit(b, "A", SELL, 100, 5, GTC); // first in queue
        limit(b, "B", SELL, 100, 5, GTC);                  // behind A
        b.replace(a.orderId(), 100, 2);                    // pure reduction → keeps A's place
        SubmitResult r = b.submit("C", BUY, MARKET, IOC, false, 0, 2);
        assertThat(r.trades().get(0).makerParticipant()).isEqualTo("A"); // still first
    }

    @Test
    void replaceWithSizeIncreaseLosesPriority() {
        OrderBook b = book();
        SubmitResult a = limit(b, "A", SELL, 100, 5, GTC);
        limit(b, "B", SELL, 100, 5, GTC);
        b.replace(a.orderId(), 100, 8);                    // increase → re-queued at the back
        SubmitResult r = b.submit("C", BUY, MARKET, IOC, false, 0, 5);
        assertThat(r.trades().get(0).makerParticipant()).isEqualTo("B"); // B is now first
    }

    @Test
    void l2AndL3ReflectTheBook() {
        OrderBook b = book();
        limit(b, "A", BUY, 100, 5, GTC);
        limit(b, "B", BUY, 100, 3, GTC);
        limit(b, "C", BUY, 99, 4, GTC);
        var l2 = b.l2(BUY, 10);
        assertThat(l2.get(0)).containsExactly(100, 8, 2); // price 100: qty 8 across 2 orders
        assertThat(l2.get(1)).containsExactly(99, 4, 1);
        assertThat(b.l3(BUY, 10)).hasSize(3); // three individual resting orders
    }
}
