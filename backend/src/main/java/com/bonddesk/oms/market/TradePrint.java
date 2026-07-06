package com.bonddesk.oms.market;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * A real executed trade from the exchange tape. {@code side} is the aggressor side.
 * {@code seq} is a local monotonic sequence so consumers (e.g. the market maker) can
 * process only trades they have not seen yet.
 */
public record TradePrint(long seq, String product, BigDecimal price, BigDecimal size, String side, Instant time) {
}
