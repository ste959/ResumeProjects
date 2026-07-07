package com.bonddesk.oms.equities;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.equities.AlpacaBrokerClient.AlpacaOrder;
import com.bonddesk.oms.matching.DeskFillEvent;
import com.bonddesk.oms.repository.OrderRepository;
import com.bonddesk.oms.service.OrderService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Polls Alpaca for the status of working equity orders and books any new fills back into
 * the OMS. This is a broker-reconciliation loop — the standard pattern for an OMS that
 * routes to an external venue rather than matching in-process: fills are pulled and
 * recorded idempotently by comparing the broker's cumulative filled quantity against ours.
 *
 * <p>Fills are published as {@link DeskFillEvent}s, so they flow through the exact same
 * {@code FillRecorder → OrderService.recordFill → position update} path as the crypto
 * matching engine — one booking pipeline across asset classes.
 */
@Component
@ConditionalOnProperty(prefix = "oms.equities", name = "enabled", havingValue = "true", matchIfMissing = true)
public class AlpacaReconciler {

    private static final Logger log = LoggerFactory.getLogger(AlpacaReconciler.class);
    private static final Set<String> TERMINAL = Set.of("canceled", "expired", "rejected");
    private static final String VENUE = "ALPACA";

    private final AlpacaProperties props;
    private final AlpacaBrokerClient broker;
    private final OrderRepository orders;
    private final OrderService orderService;
    private final ApplicationEventPublisher events;

    // Broker polling can block for seconds (the HTTP client uses a multi-second timeout). Running
    // it on its own single-thread executor keeps it entirely off Spring's shared scheduling pool,
    // so a slow broker call can never stall the live strategy / market-making @Scheduled loops.
    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "alpaca-reconciler");
        t.setDaemon(true);
        return t;
    });

    public AlpacaReconciler(AlpacaProperties props, AlpacaBrokerClient broker, OrderRepository orders,
                            OrderService orderService, ApplicationEventPublisher events) {
        this.props = props;
        this.broker = broker;
        this.orders = orders;
        this.orderService = orderService;
        this.events = events;
    }

    @PostConstruct
    void schedule() {
        long delay = Math.max(1, props.getReconcileMs());
        executor.scheduleWithFixedDelay(this::reconcileSafely, delay, delay, TimeUnit.MILLISECONDS);
    }

    @PreDestroy
    void shutdown() {
        executor.shutdownNow();
    }

    private void reconcileSafely() {
        try {
            reconcile();
        } catch (RuntimeException e) {
            log.debug("Reconcile cycle failed: {}", e.getMessage());
        }
    }

    public void reconcile() {
        if (!props.hasCredentials()) {
            return;
        }
        List<Order> working = orders.findByStatusInOrderByCreatedAtAsc(
                List.of(OrderStatus.ROUTED, OrderStatus.PARTIALLY_FILLED));
        for (Order order : working) {
            if (order.getSecurity().getAssetClass() != AssetClass.EQUITY) {
                continue;
            }
            try {
                reconcileOne(order);
            } catch (RuntimeException e) {
                log.debug("Reconcile of {} failed: {}", order.getOrderRef(), e.getMessage());
            }
        }
    }

    private void reconcileOne(Order order) {
        AlpacaOrder bo = broker.getByClientOrderId(order.getOrderRef());
        if (bo == null) {
            return;
        }
        BigDecimal brokerFilled = bo.filledQty() == null ? BigDecimal.ZERO : bo.filledQty();
        BigDecimal ourFilled = order.getFilledQuantity() == null ? BigDecimal.ZERO : order.getFilledQuantity();
        BigDecimal delta = brokerFilled.subtract(ourFilled);

        if (delta.signum() > 0 && bo.filledAvgPrice() != null) {
            // Price the incremental fill as the VWAP of the newly-filled shares, so our
            // running average matches the broker's cumulative average exactly.
            BigDecimal ourAvg = order.getAvgFillPrice() == null ? BigDecimal.ZERO : order.getAvgFillPrice();
            BigDecimal incNotional = brokerFilled.multiply(bo.filledAvgPrice()).subtract(ourFilled.multiply(ourAvg));
            BigDecimal incPrice = incNotional.divide(delta, 4, RoundingMode.HALF_UP);
            events.publishEvent(new DeskFillEvent(order.getOrderRef(), delta, incPrice, VENUE));
            log.info("Booked {} share fill for {} @ {} (broker {} of {}, status {})",
                    delta.stripTrailingZeros().toPlainString(), order.getOrderRef(), incPrice,
                    brokerFilled, order.getQuantity(), bo.status());
        }

        if (TERMINAL.contains(bo.status()) && brokerFilled.compareTo(order.getQuantity()) < 0) {
            try {
                orderService.cancel(order.getOrderRef(), "Broker " + bo.status());
            } catch (RuntimeException e) {
                log.debug("Could not cancel {} after terminal broker status: {}", order.getOrderRef(), e.getMessage());
            }
        }
    }
}
