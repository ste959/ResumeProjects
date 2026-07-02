package com.bonddesk.risk;

import java.math.BigDecimal;

/** Aggregated risk for a single portfolio, derived from the latest event per order. */
public record PortfolioRisk(
        String portfolio,
        long orderCount,
        long workingOrders,
        long rejectedOrders,
        BigDecimal filledFace
) {
}
