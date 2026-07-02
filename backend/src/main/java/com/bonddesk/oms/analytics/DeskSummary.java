package com.bonddesk.oms.analytics;

import java.math.BigDecimal;

/**
 * Firm-wide order/fill summary, computed in a single aggregate SQL query.
 *
 * @param fillRatePct filled orders as a percentage of total (derived in the service)
 */
public record DeskSummary(
        long totalOrders,
        long filledOrders,
        long workingOrders,
        long rejectedOrders,
        BigDecimal totalFilledFace,
        BigDecimal fillRatePct
) {
}
