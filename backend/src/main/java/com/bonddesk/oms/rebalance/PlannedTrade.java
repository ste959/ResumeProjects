package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.domain.OrderSide;

import java.math.BigDecimal;

/**
 * A single delta order the rebalance intends to send: the difference between the target
 * share count and the currently held share count for one name, expressed as a positive
 * quantity plus a side. {@code shortSale} flags a trade that opens or extends a short
 * position (so the venue's shortability must be checked before routing).
 */
public record PlannedTrade(
        String symbol,
        String cusip,
        OrderSide side,
        BigDecimal qty,
        BigDecimal refPrice,
        BigDecimal targetShares,
        BigDecimal currentShares,
        boolean shortSale) {
}
