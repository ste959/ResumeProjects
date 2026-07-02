package com.bonddesk.oms.analytics;

import com.bonddesk.oms.domain.OrderSide;

import java.math.BigDecimal;

/**
 * Transaction-cost-analysis (TCA) row: how well a security traded versus its benchmark
 * (indicative clean price), aggregated across all fills for a given security and side.
 *
 * @param slippageBps signed execution cost vs. benchmark in basis points — positive is
 *                    adverse (a buy filled above, or a sell filled below, the benchmark)
 */
public record ExecutionQuality(
        String cusip,
        String description,
        OrderSide side,
        long orderCount,
        BigDecimal filledFace,
        BigDecimal avgFillPrice,
        BigDecimal benchmarkPrice,
        BigDecimal slippageBps
) {
}
