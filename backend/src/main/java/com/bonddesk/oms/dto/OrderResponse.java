package com.bonddesk.oms.dto;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.TimeInForce;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/** Read model for an order, including its fills. */
public record OrderResponse(
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
        Instant updatedAt,
        List<ExecutionResponse> executions
) {

    public static OrderResponse from(Order o) {
        return new OrderResponse(
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
                o.getUpdatedAt(),
                o.getExecutions().stream().map(ExecutionResponse::from).toList()
        );
    }
}
