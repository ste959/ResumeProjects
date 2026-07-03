package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;

class OrderBookTest {

    private final OrderBook book = new OrderBook("TEST");
    private final AtomicLong ids = new AtomicLong();

    private BookOrder limit(OrderSide side, long priceTicks, long qty) {
        return new BookOrder(ids.incrementAndGet(), side, OrderType.LIMIT, priceTicks, qty, "o" + ids.get());
    }

    private BookOrder market(OrderSide side, long qty) {
        return new BookOrder(ids.incrementAndGet(), side, OrderType.MARKET, 0, qty, "o" + ids.get());
    }

    @Test
    void restingOrderThenCrossingOrderFullyMatches() {
        book.submit(limit(OrderSide.SELL, 1000000, 500)); // ask 100.00 x500
        List<Trade> trades = book.submit(limit(OrderSide.BUY, 1000000, 500));

        assertThat(trades).hasSize(1);
        assertThat(trades.get(0).quantity()).isEqualTo(500);
        assertThat(trades.get(0).priceTicks()).isEqualTo(1000000);
        assertThat(book.bestBid()).isNull();
        assertThat(book.bestAsk()).isNull();
    }

    @Test
    void partialFillLeavesRemainderResting() {
        book.submit(limit(OrderSide.SELL, 1000000, 300));
        List<Trade> trades = book.submit(limit(OrderSide.BUY, 1000000, 500));

        assertThat(trades).hasSize(1);
        assertThat(trades.get(0).quantity()).isEqualTo(300);
        // 200 of the buy rests as the new best bid
        assertThat(book.bestBid()).isEqualTo(1000000L);
        assertThat(book.bestAsk()).isNull();
        assertThat(book.restingQuantity()).isEqualTo(200);
    }

    @Test
    void tradesExecuteAtRestingPriceNotAggressorPrice() {
        book.submit(limit(OrderSide.SELL, 999000, 100)); // ask 99.90
        // Buyer willing to pay 100.10 gets price improvement — trades at 99.90
        List<Trade> trades = book.submit(limit(OrderSide.BUY, 1001000, 100));

        assertThat(trades.get(0).priceTicks()).isEqualTo(999000);
    }

    @Test
    void betterPricedRestingOrderFillsFirst() {
        BookOrder cheap = limit(OrderSide.SELL, 999000, 100); // 99.90 — better for a buyer
        BookOrder dear = limit(OrderSide.SELL, 1000000, 100); // 100.00
        book.submit(dear);
        book.submit(cheap);

        List<Trade> trades = book.submit(market(OrderSide.BUY, 150));

        assertThat(trades).hasSize(2);
        assertThat(trades.get(0).priceTicks()).isEqualTo(999000); // cheapest ask first
        assertThat(trades.get(0).quantity()).isEqualTo(100);
        assertThat(trades.get(1).priceTicks()).isEqualTo(1000000);
        assertThat(trades.get(1).quantity()).isEqualTo(50);
    }

    @Test
    void samePriceFillsInTimeOrderFifo() {
        BookOrder first = limit(OrderSide.SELL, 1000000, 100);
        BookOrder second = limit(OrderSide.SELL, 1000000, 100);
        book.submit(first);
        book.submit(second);

        List<Trade> trades = book.submit(limit(OrderSide.BUY, 1000000, 100));

        assertThat(trades).hasSize(1);
        assertThat(trades.get(0).restingId()).isEqualTo(first.id()); // earliest resting fills first
    }

    @Test
    void nonMarketableLimitRestsAndBookNeverCrosses() {
        book.submit(limit(OrderSide.BUY, 999000, 100));  // bid 99.90
        book.submit(limit(OrderSide.SELL, 1001000, 100)); // ask 100.10 — no cross

        assertThat(book.bestBid()).isEqualTo(999000L);
        assertThat(book.bestAsk()).isEqualTo(1001000L);
        assertThat(book.bestBid()).isLessThan(book.bestAsk());
    }

    @Test
    void marketOrderRemainderIsCancelledNotRested() {
        book.submit(limit(OrderSide.SELL, 1000000, 100));
        List<Trade> trades = book.submit(market(OrderSide.BUY, 500));

        assertThat(trades).hasSize(1);
        assertThat(trades.get(0).quantity()).isEqualTo(100);
        // 400 unfilled market qty is discarded, not left resting
        assertThat(book.bestBid()).isNull();
        assertThat(book.restingQuantity()).isZero();
    }

    @Test
    void cancelRemovesRestingLiquidity() {
        BookOrder resting = limit(OrderSide.SELL, 1000000, 100);
        book.submit(resting);
        assertThat(book.bestAsk()).isEqualTo(1000000L);

        assertThat(book.cancel(resting.id())).isTrue();
        assertThat(book.bestAsk()).isNull();
        // A crossing buy now finds nothing to hit and rests instead
        List<Trade> trades = book.submit(limit(OrderSide.BUY, 1000000, 100));
        assertThat(trades).isEmpty();
        assertThat(book.bestBid()).isEqualTo(1000000L);
    }
}
