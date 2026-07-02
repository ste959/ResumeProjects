package com.bonddesk.oms.dto;

import com.bonddesk.oms.domain.Position;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

/**
 * Read model for a portfolio holding. Market value is derived on the fly from the
 * security's latest clean price:
 * <pre>marketValue = netQuantity * (cleanPrice / 100)</pre>
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
        BigDecimal mark = p.getSecurity().getCleanPrice();
        BigDecimal marketValue = p.getNetQuantity()
                .multiply(mark)
                .divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
        return new PositionResponse(
                p.getPortfolio(),
                p.getSecurity().getCusip(),
                p.getSecurity().getDescription(),
                p.getNetQuantity(),
                p.getAvgCost(),
                mark,
                marketValue,
                p.getUpdatedAt()
        );
    }
}
