package com.bonddesk.risk;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

/** Firm-wide snapshot the risk dashboard/endpoint returns. */
public record DeskRiskSummary(
        long totalOrders,
        BigDecimal totalFilledFace,
        Map<String, Long> ordersByStatus,
        List<PortfolioRisk> portfolios
) {
}
