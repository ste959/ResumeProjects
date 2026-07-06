package com.bonddesk.oms.market;

import java.math.BigDecimal;
import java.time.Instant;

/** A real executed trade from the exchange tape. {@code side} is the aggressor side. */
public record TradePrint(String product, BigDecimal price, BigDecimal size, String side, Instant time) {
}
