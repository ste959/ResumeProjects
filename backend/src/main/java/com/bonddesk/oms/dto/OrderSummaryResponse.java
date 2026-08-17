package com.bonddesk.oms.dto;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.TimeInForce;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * A blotter row: everything the order list shows, aggregated on the order itself (filled quantity,
 * average price) — deliberately <em>without</em> the per-fill executions list. That keeps the paginated
 * list query free of a collection fetch (which would force in-memory pagination), so a page is a single
 * indexed, bounded query. The full fills live on the detail view ({@link OrderResponse}).
 */
public record OrderSummaryResponse(
        String orderRef,
        String cusip,
        String securityDescription,
        String portfolio,
        String trader,
        OrderSide side,
        OrderType orderType,
        TimeInForce timeInForce,
        BigDecimal quantity,
        BigDecimal limitPrice,
        OrderStatus status,
        BigDecimal filledQuantity,
        BigDecimal remainingQuantity,
        BigDecimal avgFillPrice,
        String statusReason,
        Instant createdAt,
        Instant updatedAt
) {

    public static OrderSummaryResponse from(Order o) {
        return new OrderSummaryResponse(
                o.getOrderRef(),
                o.getSecurity().getCusip(),
                o.getSecurity().getDescription(),
                o.getPortfolio(),
                o.getTrader(),
                o.getSide(),
                o.getOrderType(),
                o.getTimeInForce(),
                o.getQuantity(),
                o.getLimitPrice(),
                o.getStatus(),
                o.getFilledQuantity(),
                o.remainingQuantity(),
                o.getAvgFillPrice(),
                o.getStatusReason(),
                o.getCreatedAt(),
                o.getUpdatedAt()
        );
    }
}
