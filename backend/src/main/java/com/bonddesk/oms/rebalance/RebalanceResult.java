package com.bonddesk.oms.rebalance;

import java.math.BigDecimal;
import java.util.List;

/**
 * The outcome of a rebalance request: the plan summary, the overall status, per-trade
 * outcomes, and aggregate counts. Statuses:
 * <ul>
 *   <li>{@code DRY_RUN} — plan computed, nothing routed (the default, safe path);</li>
 *   <li>{@code BLOCKED_RISK_LIMIT} — projected gross notional exceeded the desk cap, nothing routed;</li>
 *   <li>{@code ROUTED} — delta orders were sent to the (paper) venue.</li>
 * </ul>
 */
public record RebalanceResult(
        String portfolio,
        BigDecimal grossCapital,
        String asOf,
        String status,
        int plannedTradeCount,
        BigDecimal projectedGrossNotional,
        boolean withinRiskLimit,
        int routed,
        int skipped,
        int rejected,
        List<TradeOutcome> outcomes,
        RebalancePlan plan) {

    static RebalanceResult of(RebalancePlan plan, String status, List<TradeOutcome> outcomes) {
        int routed = (int) outcomes.stream().filter(o -> o.status() == TradeOutcome.Status.ROUTED).count();
        int skipped = (int) outcomes.stream().filter(o -> o.status() == TradeOutcome.Status.SKIPPED).count();
        int rejected = (int) outcomes.stream().filter(o -> o.status() == TradeOutcome.Status.REJECTED).count();
        return new RebalanceResult(plan.portfolio(), plan.grossCapital(), plan.asOf(), status,
                plan.trades().size(), plan.projectedGrossNotional(), plan.withinRiskLimit(),
                routed, skipped, rejected, outcomes, plan);
    }

    /** A result carrying only the plan (no routing occurred). */
    static RebalanceResult planOnly(RebalancePlan plan, String status) {
        return of(plan, status, List.of());
    }
}
