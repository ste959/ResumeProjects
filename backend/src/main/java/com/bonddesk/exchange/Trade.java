package com.bonddesk.exchange;

/**
 * An execution: the aggressor (taker) crossed the spread and matched the resting (maker) order.
 * Knowing maker vs. taker is what makes microstructure analytics possible — the maker earns the
 * spread and bears adverse selection; the taker pays it. Price is the resting (maker) price.
 */
public record Trade(
        long seq,
        long priceTicks,
        long qty,
        long makerOrderId,
        long takerOrderId,
        String makerParticipant,
        String takerParticipant,
        Side aggressorSide,
        long tsNanos
) {}
