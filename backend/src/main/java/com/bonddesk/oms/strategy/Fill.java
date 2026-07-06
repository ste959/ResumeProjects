package com.bonddesk.oms.strategy;

import java.time.Instant;

/**
 * A fill produced by a strategy — either by taking liquidity (sweeping the book) or by
 * making it (a resting quote crossed by a real trade print).
 */
public record Fill(Instant time, String side, double price, double size, String liquidity) {

    public static Fill taker(Instant time, boolean buy, double price, double size) {
        return new Fill(time, buy ? "BUY" : "SELL", price, size, "TAKER");
    }

    public static Fill maker(Instant time, boolean buy, double price, double size) {
        return new Fill(time, buy ? "BUY" : "SELL", price, size, "MAKER");
    }

    public boolean isBuy() {
        return "BUY".equals(side);
    }
}
