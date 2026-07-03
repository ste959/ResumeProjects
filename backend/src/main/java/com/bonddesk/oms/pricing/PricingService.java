package com.bonddesk.oms.pricing;

import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.exception.BadRequestException;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;

/** Computes bond analytics for a security as of the current settlement date. */
@Service
public class PricingService {

    private final Clock clock;

    public PricingService(Clock clock) {
        this.clock = clock;
    }

    public BondAnalyticsResponse report(Security security) {
        LocalDate settlement = LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC);
        if (!security.getMaturityDate().isAfter(settlement)) {
            throw new BadRequestException("Security " + security.getCusip() + " has matured");
        }
        double couponDecimal = security.getCouponRate()
                .divide(BigDecimal.valueOf(100)).doubleValue(); // stored as a percentage
        BondAnalytics analytics = BondMath.analyze(settlement, security.getMaturityDate(),
                couponDecimal, security.getCleanPrice().doubleValue());
        return BondAnalyticsResponse.of(security, settlement, analytics);
    }
}
