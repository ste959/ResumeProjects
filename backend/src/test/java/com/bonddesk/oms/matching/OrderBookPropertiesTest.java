package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Property-based tests: rather than a few hand-picked cases, jqwik throws hundreds of
 * randomized order flows at the book and asserts the invariants that must hold for
 * <em>any</em> sequence of orders. These are the guarantees a real exchange lives or
 * dies by.
 */
class OrderBookPropertiesTest {

    /** A generated order instruction. */
    record Spec(OrderSide side, OrderType type, long priceTicks, long qty) {}

    @Provide
    Arbitrary<List<Spec>> orderFlow() {
        Arbitrary<OrderSide> sides = Arbitraries.of(OrderSide.BUY, OrderSide.SELL);
        // Mostly limit orders, occasional market orders.
        Arbitrary<OrderType> types = Arbitraries.frequency(
                net.jqwik.api.Tuple.of(4, OrderType.LIMIT),
                net.jqwik.api.Tuple.of(1, OrderType.MARKET));
        Arbitrary<Long> prices = Arbitraries.longs().between(990_000L, 1_010_000L); // 99.00–101.00
        Arbitrary<Long> qtys = Arbitraries.longs().between(1L, 1_000L);
        Arbitrary<Spec> spec = Combinators.combine(sides, types, prices, qtys).as(Spec::new);
        return spec.list().ofMaxSize(250);
    }

    /** Apply a flow to a fresh book, keeping every order and every trade for assertions. */
    private static Result run(List<Spec> specs) {
        OrderBook book = new OrderBook("PROP");
        Map<Long, BookOrder> all = new HashMap<>();
        List<Trade> trades = new ArrayList<>();
        long id = 0;
        for (Spec s : specs) {
            BookOrder o = new BookOrder(++id, s.side(), s.type(), s.priceTicks(), s.qty(), "o" + id);
            all.put(o.id(), o);
            trades.addAll(book.submit(o));
        }
        return new Result(book, all, trades);
    }

    record Result(OrderBook book, Map<Long, BookOrder> all, List<Trade> trades) {}

    @Property(tries = 300)
    void bookIsNeverCrossed(@ForAll("orderFlow") List<Spec> specs) {
        OrderBook book = run(specs).book();
        Long bid = book.bestBid();
        Long ask = book.bestAsk();
        if (bid != null && ask != null) {
            // A resting bid must always be strictly below the best ask — otherwise they
            // would have matched.
            assertThat(bid).isLessThan(ask);
        }
    }

    @Property(tries = 300)
    void quantityIsConserved(@ForAll("orderFlow") List<Spec> specs) {
        Result r = run(specs);
        long filledAcrossAllOrders = r.all().values().stream()
                .mapToLong(o -> o.quantity() - o.remaining())
                .sum();
        long tradedTwice = r.trades().stream().mapToLong(Trade::quantity).sum() * 2;
        // Every unit traded reduces exactly two orders (a buyer and a seller) by that amount.
        assertThat(filledAcrossAllOrders).isEqualTo(tradedTwice);
    }

    @Property(tries = 300)
    void noOrderEverTradesThroughItsLimit(@ForAll("orderFlow") List<Spec> specs) {
        Result r = run(specs);
        for (Trade t : r.trades()) {
            BookOrder aggressor = r.all().get(t.aggressorId());
            BookOrder resting = r.all().get(t.restingId());
            checkPriceHonoured(aggressor, t.priceTicks());
            checkPriceHonoured(resting, t.priceTicks());
        }
    }

    private static void checkPriceHonoured(BookOrder order, long tradePrice) {
        if (order.type() == OrderType.MARKET) {
            return; // market orders accept any price
        }
        if (order.side() == OrderSide.BUY) {
            assertThat(tradePrice).isLessThanOrEqualTo(order.priceTicks()); // never overpay
        } else {
            assertThat(tradePrice).isGreaterThanOrEqualTo(order.priceTicks()); // never undersell
        }
    }

    @Property(tries = 300)
    void restingQuantityMatchesTheBook(@ForAll("orderFlow") List<Spec> specs) {
        Result r = run(specs);
        long restingFromOrders = r.all().values().stream()
                .filter(BookOrder::isActive)
                .mapToLong(BookOrder::remaining)
                .sum();
        assertThat(r.book().restingQuantity()).isEqualTo(restingFromOrders);
    }
}
