package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.TimeInForce;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.bonddesk.oms.exception.InvalidStateTransitionException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** Exercises compliance-at-entry and the full order lifecycle against a real database. */
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceIntegrationTest {

    private static final String TREASURY = "912828YK0";   // AAA, price ~97.82
    private static final String HIGH_YIELD = "122017PZ2"; // B+ (sub-investment-grade)
    private static final String RESTRICTED = "999999XX9"; // on the restricted list

    @Autowired
    private OrderService orders;

    @Autowired
    private PositionService positions;

    private CreateOrderRequest req(String cusip, OrderSide side, String qty) {
        return new CreateOrderRequest(cusip, "PORT-INT-" + System.nanoTime(), "trader1",
                side, OrderType.MARKET, TimeInForce.DAY, new BigDecimal(qty), null);
    }

    @Test
    void validOrderIsAcceptedAsNew() {
        Order order = orders.create(req(TREASURY, OrderSide.BUY, "1000000"));

        assertThat(order.getStatus()).isEqualTo(OrderStatus.NEW);
        assertThat(order.getOrderRef()).isNotBlank();
        assertThat(order.getStatusReason()).isNull();
    }

    @Test
    void restrictedSecurityIsRejectedAtEntry() {
        Order order = orders.create(req(RESTRICTED, OrderSide.BUY, "1000000"));

        assertThat(order.getStatus()).isEqualTo(OrderStatus.REJECTED);
        assertThat(order.getStatusReason()).containsIgnoringCase("restricted");
    }

    @Test
    void buyingBelowMinimumRatingIsRejected() {
        Order order = orders.create(req(HIGH_YIELD, OrderSide.BUY, "1000000"));

        assertThat(order.getStatus()).isEqualTo(OrderStatus.REJECTED);
        assertThat(order.getStatusReason()).containsIgnoringCase("below the desk minimum");
    }

    @Test
    void sellingBelowMinimumRatingIsAllowed() {
        Order order = orders.create(req(HIGH_YIELD, OrderSide.SELL, "1000000"));

        assertThat(order.getStatus()).isEqualTo(OrderStatus.NEW);
    }

    @Test
    void orderExceedingNotionalLimitIsRejected() {
        // 30MM face * ~97.82% ≈ 29.3MM notional > 25MM per-order cap
        Order order = orders.create(req(TREASURY, OrderSide.BUY, "30000000"));

        assertThat(order.getStatus()).isEqualTo(OrderStatus.REJECTED);
        assertThat(order.getStatusReason()).containsIgnoringCase("per-order limit");
    }

    @Test
    void fullLifecycleFillsOrderAndUpdatesPosition() {
        CreateOrderRequest request = new CreateOrderRequest(TREASURY, "PORT-LC", "trader1",
                OrderSide.BUY, OrderType.MARKET, TimeInForce.DAY, new BigDecimal("1000000"), null);

        Order created = orders.create(request);
        orders.stage(created.getOrderRef());
        Order routed = orders.route(created.getOrderRef());
        assertThat(routed.getStatus()).isEqualTo(OrderStatus.ROUTED);

        Order partial = orders.recordFill(created.getOrderRef(), new BigDecimal("600000"),
                new BigDecimal("98.0000"), "TW");
        assertThat(partial.getStatus()).isEqualTo(OrderStatus.PARTIALLY_FILLED);
        assertThat(partial.getFilledQuantity()).isEqualByComparingTo("600000");

        Order filled = orders.recordFill(created.getOrderRef(), new BigDecimal("400000"),
                new BigDecimal("98.5000"), "TW");
        assertThat(filled.getStatus()).isEqualTo(OrderStatus.FILLED);
        assertThat(filled.remainingQuantity()).isEqualByComparingTo("0");
        // Weighted avg fill: (600k*98.00 + 400k*98.50) / 1,000k = 98.20
        assertThat(filled.getAvgFillPrice()).isEqualByComparingTo("98.2000");

        List<Position> book = positions.forPortfolio("PORT-LC");
        assertThat(book).hasSize(1);
        assertThat(book.get(0).getNetQuantity()).isEqualByComparingTo("1000000");
        assertThat(book.get(0).getAvgCost()).isEqualByComparingTo("98.2000");
    }

    @Test
    void fillIsClampedToRemainingQuantity() {
        Order created = orders.create(req(TREASURY, OrderSide.BUY, "1000000"));
        orders.stage(created.getOrderRef());
        orders.route(created.getOrderRef());

        Order filled = orders.recordFill(created.getOrderRef(), new BigDecimal("5000000"),
                new BigDecimal("98.0000"), "TW");

        assertThat(filled.getStatus()).isEqualTo(OrderStatus.FILLED);
        assertThat(filled.getFilledQuantity()).isEqualByComparingTo("1000000");
    }

    @Test
    void routingBeforeStagingIsRejected() {
        Order created = orders.create(req(TREASURY, OrderSide.BUY, "1000000"));

        assertThatThrownBy(() -> orders.route(created.getOrderRef()))
                .isInstanceOf(InvalidStateTransitionException.class);
    }
}
