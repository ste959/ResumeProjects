package com.bonddesk.oms.dto;

import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.util.Pricing;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Read model for a portfolio holding. Market value is derived on the fly from the best
 * available mark (a live price when one is supplied, otherwise the security's latest
 * indicative price) using the asset class's quoting convention:
 * <pre>bonds:    marketValue = netQuantity * mark / 100   (mark is % of par)
 * equities: marketValue = shares      * mark          (mark is $/share)</pre>
 */
public record PositionResponse(
        String portfolio,
        String cusip,
        String securityDescription,
        BigDecimal netQuantity,
        BigDecimal avgCost,
        BigDecimal markPrice,
        BigDecimal marketValue,
        Instant updatedAt
) {

    public static PositionResponse from(Position p) {
        return from(p, null);
    }

    /** @param liveMark a live mark price to prefer over the stored indicative price, or null. */
    public static PositionResponse from(Position p, BigDecimal liveMark) {
        Security s = p.getSecurity();
        BigDecimal mark = liveMark != null ? liveMark : s.getCleanPrice();
        BigDecimal marketValue = Pricing.notional(s, p.getNetQuantity(), mark);
        return new PositionResponse(
                p.getPortfolio(),
                s.getCusip(),
                s.getDescription(),
                p.getNetQuantity(),
                p.getAvgCost(),
                mark,
                marketValue,
                p.getUpdatedAt()
        );
    }
}
