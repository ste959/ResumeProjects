package com.bonddesk.oms.equities;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Top-of-book (NBBO) quote for a listed equity. The free Alpaca IEX feed provides
 * best-bid/ask rather than full depth, so — unlike the crypto order book — this is a
 * single level per side.
 */
public record EquityQuote(
        String symbol,
        BigDecimal bid,
        BigDecimal ask,
        BigDecimal bidSize,
        BigDecimal askSize,
        BigDecimal last,
        Instant time
) {
}
