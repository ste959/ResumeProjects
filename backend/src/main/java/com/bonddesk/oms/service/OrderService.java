package com.bonddesk.oms.service;

import com.bonddesk.oms.compliance.ComplianceResult;
import com.bonddesk.oms.compliance.ComplianceService;
import com.bonddesk.oms.domain.Execution;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.bonddesk.oms.event.OrderEvent;
import com.bonddesk.oms.event.OrderEventPublisher;
import com.bonddesk.oms.exception.BadRequestException;
import com.bonddesk.oms.exception.InvalidStateTransitionException;
import com.bonddesk.oms.exception.NotFoundException;
import com.bonddesk.oms.matching.MatchingGateway;
import com.bonddesk.oms.repository.OrderRepository;
import com.bonddesk.oms.repository.SecurityRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.util.List;
import java.util.UUID;

/**
 * Owns the fixed-income order lifecycle: entry (with pre-trade compliance), staging,
 * routing, filling, and cancellation. State changes go through {@link #transitionTo}
 * so the legal-transition rules in {@link OrderStatus} are enforced in one place, and
 * every change emits an {@link OrderEvent}.
 */
@Service
public class OrderService {

    private static final Logger log = LoggerFactory.getLogger(OrderService.class);

    /** Statuses an order can be in while still working in the market. */
    static final List<OrderStatus> WORKING = List.of(OrderStatus.ROUTED, OrderStatus.PARTIALLY_FILLED);

    private final OrderRepository orders;
    private final SecurityRepository securities;
    private final ComplianceService compliance;
    private final PositionService positions;
    private final OrderEventPublisher events;
    private final MatchingGateway matching;
    private final Clock clock;

    public OrderService(OrderRepository orders, SecurityRepository securities,
                        ComplianceService compliance, PositionService positions,
                        OrderEventPublisher events, MatchingGateway matching, Clock clock) {
        this.orders = orders;
        this.securities = securities;
        this.compliance = compliance;
        this.positions = positions;
        this.events = events;
        this.matching = matching;
        this.clock = clock;
    }

    // ---------- Reads ----------

    @Transactional(readOnly = true)
    public Order get(String orderRef) {
        Order order = orders.findByOrderRef(orderRef)
                .orElseThrow(() -> new NotFoundException("No order with ref " + orderRef));
        order.getExecutions().size(); // initialise lazy fills while the session is open
        return order;
    }

    @Transactional(readOnly = true)
    public List<Order> list(OrderStatus status, String portfolio) {
        List<Order> result;
        if (status != null) {
            result = orders.findByStatusOrderByCreatedAtDesc(status);
        } else if (portfolio != null && !portfolio.isBlank()) {
            result = orders.findByPortfolioOrderByCreatedAtDesc(portfolio);
        } else {
            result = orders.findAllByOrderByCreatedAtDesc();
        }
        result.forEach(o -> o.getExecutions().size()); // initialise lazy fills in-session
        return result;
    }

    @Transactional(readOnly = true)
    public List<Order> workingOrders() {
        return orders.findByStatusInOrderByCreatedAtAsc(WORKING);
    }

    // ---------- Lifecycle ----------

    /**
     * Stage a new order. Runs pre-trade compliance at entry: a breach does not throw —
     * the order is persisted as {@link OrderStatus#REJECTED} with the reason recorded,
     * which mirrors how a real desk keeps an audit trail of blocked orders.
     */
    @Transactional
    public Order create(CreateOrderRequest req) {
        Security security = securities.findById(req.cusip())
                .orElseThrow(() -> new NotFoundException("No security with cusip " + req.cusip()));

        if (req.orderType() == OrderType.LIMIT && req.limitPrice() == null) {
            throw new BadRequestException("limitPrice is required for LIMIT orders");
        }

        Order order = new Order();
        order.setOrderRef(UUID.randomUUID().toString());
        order.setSecurity(security);
        order.setPortfolio(req.portfolio());
        order.setTrader(req.trader());
        order.setSide(req.side());
        order.setOrderType(req.orderType());
        order.setTimeInForce(req.timeInForce());
        order.setQuantity(req.quantity());
        order.setLimitPrice(req.orderType() == OrderType.LIMIT ? req.limitPrice() : null);
        order.setStatus(OrderStatus.NEW);
        order.setCreatedAt(clock.instant());
        order.setUpdatedAt(clock.instant());

        ComplianceResult result = compliance.check(order);
        if (!result.approved()) {
            order.setStatus(OrderStatus.REJECTED);
            order.setStatusReason(result.summary());
            Order saved = orders.save(order);
            log.info("Order {} REJECTED at entry: {}", saved.getOrderRef(), result.summary());
            publish(OrderEvent.Type.ORDER_REJECTED, saved);
            return saved;
        }

        Order saved = orders.save(order);
        log.info("Order {} created: {} {} {} @ {}", saved.getOrderRef(), saved.getSide(),
                saved.getQuantity(), saved.getSecurity().getCusip(),
                saved.getLimitPrice() != null ? saved.getLimitPrice() : "MKT");
        publish(OrderEvent.Type.ORDER_CREATED, saved);
        return saved;
    }

    /** Trader releases the order (NEW → STAGED). */
    @Transactional
    public Order stage(String orderRef) {
        Order order = get(orderRef);
        transitionTo(order, OrderStatus.STAGED);
        return finish(order, OrderEvent.Type.ORDER_STAGED);
    }

    /** Send the order to the matching engine (STAGED → ROUTED); marketable quantity fills now. */
    @Transactional
    public Order route(String orderRef) {
        Order order = get(orderRef);
        transitionTo(order, OrderStatus.ROUTED);
        Order routed = finish(order, OrderEvent.Type.ORDER_ROUTED);
        // Submit to the book. Any fills are recorded synchronously via DeskFillEvent →
        // FillRecorder → recordFill, mutating this same (managed) order before we return.
        matching.route(routed);
        return routed;
    }

    /** Cancel any non-terminal order. */
    @Transactional
    public Order cancel(String orderRef, String reason) {
        Order order = get(orderRef);
        transitionTo(order, OrderStatus.CANCELLED);
        order.setStatusReason(reason == null || reason.isBlank() ? "Cancelled by user" : reason);
        Order cancelled = finish(order, OrderEvent.Type.ORDER_CANCELLED);
        matching.cancel(cancelled); // pull any resting remainder from the book
        return cancelled;
    }

    /**
     * Record a fill against a working order. Quantity is clamped to what remains, the
     * average fill price is recomputed from all executions, the order transitions to
     * PARTIALLY_FILLED or FILLED, and the portfolio position is updated atomically.
     */
    @Transactional
    public Order recordFill(String orderRef, BigDecimal fillQty, BigDecimal price, String venue) {
        Order order = get(orderRef);
        return recordFill(order, fillQty, price, venue);
    }

    @Transactional
    public Order recordFill(Order order, BigDecimal fillQty, BigDecimal price, String venue) {
        if (!WORKING.contains(order.getStatus())) {
            throw new InvalidStateTransitionException(order.getOrderRef(), order.getStatus(), OrderStatus.PARTIALLY_FILLED);
        }
        if (fillQty == null || fillQty.signum() <= 0) {
            throw new BadRequestException("fill quantity must be positive");
        }

        BigDecimal applied = fillQty.min(order.remainingQuantity());
        if (applied.signum() <= 0) {
            throw new BadRequestException("order has no remaining quantity to fill");
        }

        order.addExecution(new Execution(applied, price, venue, clock.instant()));
        order.setFilledQuantity(order.getFilledQuantity().add(applied));
        order.setAvgFillPrice(weightedAvgFillPrice(order));

        boolean fullyFilled = order.isFullyFilled();
        transitionTo(order, fullyFilled ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED);

        positions.applyFill(order.getPortfolio(), order.getSecurity(), order.getSide(), applied, price);

        Order saved = orders.save(order);
        log.info("Order {} {} fill {} @ {} ({}/{} filled)", saved.getOrderRef(),
                fullyFilled ? "FILLED" : "PARTIAL", applied, price, saved.getFilledQuantity(), saved.getQuantity());
        publish(fullyFilled ? OrderEvent.Type.ORDER_FILLED : OrderEvent.Type.ORDER_PARTIALLY_FILLED, saved);
        return saved;
    }

    // ---------- Internals ----------

    private void transitionTo(Order order, OrderStatus target) {
        if (!order.getStatus().canTransitionTo(target)) {
            throw new InvalidStateTransitionException(order.getOrderRef(), order.getStatus(), target);
        }
        order.setStatus(target);
        order.setUpdatedAt(clock.instant());
    }

    private Order finish(Order order, OrderEvent.Type type) {
        Order saved = orders.save(order);
        publish(type, saved);
        return saved;
    }

    private void publish(OrderEvent.Type type, Order order) {
        events.publish(OrderEvent.of(type, order, clock.instant()));
    }

    private BigDecimal weightedAvgFillPrice(Order order) {
        BigDecimal notional = BigDecimal.ZERO;
        BigDecimal qty = BigDecimal.ZERO;
        for (Execution e : order.getExecutions()) {
            notional = notional.add(e.getQuantity().multiply(e.getPrice()));
            qty = qty.add(e.getQuantity());
        }
        return qty.signum() == 0 ? null : notional.divide(qty, 4, RoundingMode.HALF_UP);
    }
}
