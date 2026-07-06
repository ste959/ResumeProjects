package com.bonddesk.oms.backtest;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * One event from the captured L2 log: a book snapshot level ({@code SNAP}), an incremental
 * level update ({@code UPD}), or a trade print ({@code TRD}). {@code side} is B (bid) / A
 * (ask) for book events, or the aggressor side for trades.
 */
public record L2Event(long seq, Instant ts, String product, String kind, String side,
                      BigDecimal price, BigDecimal size) {

    public boolean isBid() {
        return "B".equals(side);
    }

    public boolean isSnapshot() {
        return "SNAP".equals(kind);
    }

    public boolean isUpdate() {
        return "UPD".equals(kind);
    }

    public boolean isTrade() {
        return "TRD".equals(kind);
    }
}
