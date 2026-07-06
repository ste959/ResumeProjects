package com.bonddesk.oms.equities;

import java.math.BigDecimal;
import java.time.Instant;

/** A single equity trade print from the live feed. {@code seq} is a local cursor. */
public record EquityTrade(long seq, String symbol, BigDecimal price, BigDecimal size, Instant time) {
}
