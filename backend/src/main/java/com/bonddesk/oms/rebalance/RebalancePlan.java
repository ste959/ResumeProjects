package com.bonddesk.oms.rebalance;

import java.math.BigDecimal;
import java.util.List;

/**
 * The computed set of delta orders for a rebalance, before any of them are routed. A plan
 * is pure arithmetic over the target book and current positions — building it has no side
 * effects, which is what makes the dry-run preview safe.
 */
public record RebalancePlan(
        String portfolio,
        BigDecimal grossCapital,
        String asOf,
        List<PlannedTrade> trades,
        BigDecimal projectedGrossNotional,
        boolean withinRiskLimit) {
}
