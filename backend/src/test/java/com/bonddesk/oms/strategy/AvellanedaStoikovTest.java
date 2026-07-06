package com.bonddesk.oms.strategy;

import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.LiveOrderBook.Level;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class AvellanedaStoikovTest {

    private static final Instant T = Instant.parse("2026-07-02T00:00:00Z");

    private static LiveOrderBook book() {
        LiveOrderBook b = new LiveOrderBook("BTC-USD");
        b.resetTo(List.of(new Level(new BigDecimal("99.99"), new BigDecimal("10"))),
                List.of(new Level(new BigDecimal("100.01"), new BigDecimal("10"))));
        return b;
    }

    private static double[] quote(double inventory) {
        AvellanedaStoikovMaker mm = new AvellanedaStoikovMaker(0.3, 1.5, 60, 0.05);
        StrategyRun run = new StrategyRun("AS", "BTC-USD", mm, T);
        if (inventory != 0) {
            run.book().apply(Fill.taker(T, inventory > 0, 100, Math.abs(inventory)));
        }
        MarketState state = new MarketState("BTC-USD", 99.99, 100.01, 100, 100, 0.01, 0);
        mm.step(new StrategyContext(state, book(), run, T));
        return new double[]{run.quoteBid(), run.quoteAsk()};
    }

    @Test
    void flatInventoryQuotesAreCenteredOnMid() {
        double[] q = quote(0);
        assertThat(q[0]).isLessThan(q[1]);                 // bid < ask
        double reservation = (q[0] + q[1]) / 2;
        assertThat(reservation).isCloseTo(100.0, org.assertj.core.api.Assertions.within(0.05));
    }

    @Test
    void longInventorySkewsQuotesDownToSell() {
        double[] q = quote(5.0); // long → want to sell → skew reservation below mid
        double reservation = (q[0] + q[1]) / 2;
        assertThat(reservation).isLessThan(100.0);
    }

    @Test
    void shortInventorySkewsQuotesUpToBuy() {
        double[] q = quote(-5.0);
        double reservation = (q[0] + q[1]) / 2;
        assertThat(reservation).isGreaterThan(100.0);
    }
}
