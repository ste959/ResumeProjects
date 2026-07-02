package com.bonddesk.oms.event;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Immutable notification that something happened to an order. Published on every
 * lifecycle change so downstream consumers (position keeper, market-data driven
 * execution simulator, audit) can react without the OMS knowing who they are.
 */
public record OrderEvent(
        Type type,
        String orderRef,
        String cusip,
        String portfolio,
        OrderStatus status,
        BigDecimal quantity,
        BigDecimal filledQuantity,
        Instant occurredAt
) {

    public enum Type {
        ORDER_CREATED,
        ORDER_STAGED,
        ORDER_ROUTED,
        ORDER_PARTIALLY_FILLED,
        ORDER_FILLED,
        ORDER_CANCELLED,
        ORDER_REJECTED
    }

    public static OrderEvent of(Type type, Order order, Instant occurredAt) {
        return new OrderEvent(
                type,
                order.getOrderRef(),
                order.getSecurity().getCusip(),
                order.getPortfolio(),
                order.getStatus(),
                order.getQuantity(),
                order.getFilledQuantity(),
                occurredAt
        );
    }
}
