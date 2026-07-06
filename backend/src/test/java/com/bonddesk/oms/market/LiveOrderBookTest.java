package com.bonddesk.oms.market;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

class LiveOrderBookTest {

    @Test
    void sizeAtIsExactLevelWhileSizeAtOrBetterIsCumulative() {
        LiveOrderBook book = new LiveOrderBook("X");
        book.apply(true, new BigDecimal("100"), new BigDecimal("5")); // bid 100 x5
        book.apply(true, new BigDecimal("99"), new BigDecimal("3"));  // bid 99 x3

        // sizeAt = just that level — the correct queue-ahead measure (better levels are
        // cleared by any trade that reaches you).
        assertThat(book.sizeAt(true, new BigDecimal("100"))).isEqualByComparingTo("5");
        assertThat(book.sizeAt(true, new BigDecimal("99"))).isEqualByComparingTo("3");
        assertThat(book.sizeAt(true, new BigDecimal("98"))).isEqualByComparingTo("0"); // empty level

        // sizeAtOrBetter includes better levels — using it for queue-ahead over-counts (the bug).
        assertThat(book.sizeAtOrBetter(true, new BigDecimal("99"))).isEqualByComparingTo("8");
    }
}
