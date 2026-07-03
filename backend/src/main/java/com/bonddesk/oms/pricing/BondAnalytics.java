package com.bonddesk.oms.pricing;

/**
 * Risk analytics for a fixed-rate bond, all derived from first principles (discounted
 * cash flows), not stored.
 *
 * @param yieldToMaturity  annualised YTM as a decimal (0.0425 = 4.25%)
 * @param accruedInterest  interest accrued since the last coupon, per 100 face
 * @param dirtyPrice       clean price + accrued interest, per 100 face
 * @param macaulayDuration cash-flow-weighted average time to receipt, in years
 * @param modifiedDuration % price change for a 100bp yield move (approx), in years
 * @param convexity        second-order price sensitivity to yield, in years²
 * @param dv01             dollar value of a 1bp yield move, per 100 face
 */
public record BondAnalytics(
        double yieldToMaturity,
        double accruedInterest,
        double dirtyPrice,
        double macaulayDuration,
        double modifiedDuration,
        double convexity,
        double dv01
) {
}
