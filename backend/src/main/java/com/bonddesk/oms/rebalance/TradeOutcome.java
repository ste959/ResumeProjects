package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.domain.OrderSide;

import java.math.BigDecimal;

/**
 * What actually happened to one {@link PlannedTrade} when the rebalance tried to route it:
 * {@code ROUTED} (order created/staged/routed, detail = order ref), {@code SKIPPED} (e.g. the
 * name is not shortable, detail = reason), or {@code REJECTED} (an exception on the
 * create/stage/route path, detail = message). One bad name never aborts the batch.
 */
public record TradeOutcome(
        String symbol,
        String cusip,
        OrderSide side,
        BigDecimal qty,
        Status status,
        String detail) {

    public enum Status { ROUTED, SKIPPED, REJECTED }

    static TradeOutcome routed(PlannedTrade t, String orderRef) {
        return new TradeOutcome(t.symbol(), t.cusip(), t.side(), t.qty(), Status.ROUTED, orderRef);
    }

    static TradeOutcome skipped(PlannedTrade t, String reason) {
        return new TradeOutcome(t.symbol(), t.cusip(), t.side(), t.qty(), Status.SKIPPED, reason);
    }

    static TradeOutcome rejected(PlannedTrade t, String reason) {
        return new TradeOutcome(t.symbol(), t.cusip(), t.side(), t.qty(), Status.REJECTED, reason);
    }
}
