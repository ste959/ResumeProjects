package com.bonddesk.oms.pricing;

import com.bonddesk.oms.domain.Security;

import java.time.LocalDate;

/** API view of a bond's computed analytics. */
public record BondAnalyticsResponse(
        String cusip,
        String description,
        LocalDate settlementDate,
        double cleanPrice,
        double yieldToMaturityPct,
        double accruedInterest,
        double dirtyPrice,
        double macaulayDuration,
        double modifiedDuration,
        double convexity,
        double dv01
) {
    public static BondAnalyticsResponse of(Security s, LocalDate settlement, BondAnalytics a) {
        return new BondAnalyticsResponse(
                s.getCusip(),
                s.getDescription(),
                settlement,
                s.getCleanPrice().doubleValue(),
                a.yieldToMaturity() * 100.0,
                round(a.accruedInterest()),
                round(a.dirtyPrice()),
                round(a.macaulayDuration()),
                round(a.modifiedDuration()),
                round(a.convexity()),
                round(a.dv01())
        );
    }

    private static double round(double v) {
        return Math.round(v * 1e6) / 1e6;
    }
}
