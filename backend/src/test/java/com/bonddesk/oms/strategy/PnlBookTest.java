package com.bonddesk.oms.strategy;

import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

class PnlBookTest {

    private static final Instant T = Instant.parse("2026-07-02T00:00:00Z");

    @Test
    void averageCostAndRealizedPnl() {
        PnlBook book = new PnlBook();
        book.apply(Fill.taker(T, true, 100, 1));   // long 1 @100
        book.apply(Fill.taker(T, true, 102, 1));   // long 2 @avg 101

        assertThat(book.position()).isEqualTo(2);
        assertThat(book.avgCost()).isCloseTo(101, within(1e-9));
        assertThat(book.realized()).isEqualTo(0);

        book.apply(Fill.taker(T, false, 110, 1));  // sell 1 @110 → realize 9
        assertThat(book.position()).isEqualTo(1);
        assertThat(book.realized()).isCloseTo(9, within(1e-9));
        assertThat(book.avgCost()).isCloseTo(101, within(1e-9)); // unchanged while reducing
    }

    @Test
    void unrealizedMarksToMarket() {
        PnlBook book = new PnlBook();
        book.apply(Fill.taker(T, true, 100, 2)); // long 2 @100
        assertThat(book.unrealized(105)).isCloseTo(10, within(1e-9));
        assertThat(book.totalPnl(105)).isCloseTo(10, within(1e-9));
    }

    @Test
    void flipThroughZeroRepricesResidual() {
        PnlBook book = new PnlBook();
        book.apply(Fill.taker(T, true, 100, 1));   // long 1 @100
        book.apply(Fill.taker(T, false, 100, 3));  // sell 3 → close 1 (pnl 0), short 2 @100
        assertThat(book.position()).isEqualTo(-2);
        assertThat(book.avgCost()).isCloseTo(100, within(1e-9));
    }
}
