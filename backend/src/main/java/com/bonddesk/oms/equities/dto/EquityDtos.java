package com.bonddesk.oms.equities.dto;

import java.math.BigDecimal;
import java.time.Instant;

/** API view models for the equities market-data endpoints. */
public final class EquityDtos {

    private EquityDtos() {
    }

    public record EquityQuoteView(
            String symbol,
            BigDecimal bid,
            BigDecimal ask,
            BigDecimal mid,
            BigDecimal spread,
            BigDecimal spreadBps,
            BigDecimal bidSize,
            BigDecimal askSize,
            BigDecimal last
    ) {
    }

    public record EquityTradeView(long seq, String symbol, BigDecimal price, BigDecimal size, Instant time) {
    }

    public record AccountView(String status, BigDecimal cash, BigDecimal buyingPower,
                              BigDecimal equity, String currency, boolean connected) {
    }
}
