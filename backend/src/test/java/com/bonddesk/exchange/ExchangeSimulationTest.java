package com.bonddesk.exchange;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Random;

import static org.assertj.core.api.Assertions.assertThat;

/** The market comes alive: maker + agent flow drive the engine, producing real matches to measure. */
class ExchangeSimulationTest {

    @Test
    void makerAndFlowProduceALiveMarket() {
        MarketMaker mm = new MarketMaker(2, 1, 5, 200);   // half-spread 2t, skew 1t/lot, size 5, maxInv 200
        OrderBook book = new OrderBook("BTC-USD", new CompositeListener(List.of(mm)), System::nanoTime);
        FlowGenerator flow = new FlowGenerator(7, 8, 0.35);

        Random rng = new Random(1);
        long fair = 50_000;
        for (int tick = 0; tick < 3_000; tick++) {
            long move = rng.nextInt(3) - 1;               // fair random walk, ±1 tick
            fair += move;
            flow.step(book, fair, move, 6);               // flow hits the maker's stale quote
            mm.requote(book, fair);                       // maker refreshes for next tick
        }

        System.out.printf("%n=== Exchange simulation ===%n");
        System.out.printf("  trades matched : %,d%n", book.tradeCount());
        System.out.printf("  maker fills    : %,d%n", mm.fills());
        System.out.printf("  maker inventory: %d lots%n", mm.inventory());
        System.out.printf("  maker P&L      : %,d tick·lots (at fair %d)%n%n", mm.pnl(fair), fair);

        assertThat(book.tradeCount()).isGreaterThan(100);                 // a live, trading market
        assertThat(mm.fills()).isGreaterThan(0);                          // the maker got lifted
        assertThat(Math.abs(mm.inventory())).isLessThan(260);            // inventory stays bounded (maxInv + a quote)
        assertThat(book.restingQuantity()).isGreaterThanOrEqualTo(0);    // book stays consistent
    }
}
