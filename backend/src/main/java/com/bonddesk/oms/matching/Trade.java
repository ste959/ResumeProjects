package com.bonddesk.oms.matching;

/**
 * An execution produced when an aggressing order matches a resting order. Carries both
 * order ids and both owner refs (null when a side is non-desk liquidity) so the OMS can
 * record fills for whichever side(s) are its own orders. Trades always print at the
 * resting order's price (standard price-improvement-to-the-aggressor convention).
 *
 * @param priceTicks execution price in ticks (price × 10,000)
 * @param quantity   face quantity executed
 */
public record Trade(
        long aggressorId,
        long restingId,
        String buyRef,
        String sellRef,
        long priceTicks,
        long quantity,
        long sequence
) {
}
