package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Stands in for a real execution venue (Tradeweb, Bloomberg, a broker) so the OMS can
 * be demoed end-to-end without external connectivity. On a fixed cadence it looks at
 * every working order and probabilistically returns a partial or full fill at a price
 * near the security's indicative level, respecting LIMIT marketability.
 *
 * <p>Disabled under the {@code test} profile (see {@code oms.execution.simulator.enabled})
 * so tests drive fills deterministically through the API instead.
 */
@Component
@ConditionalOnProperty(prefix = "oms.execution.simulator", name = "enabled", havingValue = "true", matchIfMissing = true)
public class ExecutionSimulator {

    private static final Logger log = LoggerFactory.getLogger(ExecutionSimulator.class);
    private static final String VENUE = "SIM";

    /** Chance a given working order receives a fill on any one tick. */
    private static final double FILL_PROBABILITY = 0.6;
    /** Max price wander from the indicative level, in points of par. */
    private static final BigDecimal MAX_SLIPPAGE = new BigDecimal("0.15");

    private final OrderService orders;

    public ExecutionSimulator(OrderService orders) {
        this.orders = orders;
    }

    @Scheduled(fixedDelayString = "${oms.execution.simulator.interval-ms:2000}")
    public void tick() {
        for (Order order : orders.workingOrders()) {
            if (ThreadLocalRandom.current().nextDouble() > FILL_PROBABILITY) {
                continue;
            }
            try {
                attemptFill(order);
            } catch (RuntimeException ex) {
                // A concurrent cancel/fill can invalidate this order mid-tick; skip it.
                log.debug("Skipped fill for {}: {}", order.getOrderRef(), ex.getMessage());
            }
        }
    }

    private void attemptFill(Order order) {
        BigDecimal price = simulatedPrice(order);
        if (!isMarketable(order, price)) {
            return;
        }
        BigDecimal remaining = order.remainingQuantity();
        // Fill 25%–100% of what's left, rounded to a round lot of 1,000 face.
        double fraction = ThreadLocalRandom.current().nextDouble(0.25, 1.0001);
        BigDecimal fillQty = remaining.multiply(BigDecimal.valueOf(fraction))
                .divide(BigDecimal.valueOf(1000), 0, RoundingMode.UP)
                .multiply(BigDecimal.valueOf(1000))
                .min(remaining);
        if (fillQty.signum() <= 0) {
            return;
        }
        orders.recordFill(order.getOrderRef(), fillQty, price, VENUE);
    }

    /** Indicative level plus a small random slippage. */
    private BigDecimal simulatedPrice(Order order) {
        BigDecimal base = order.getSecurity().getCleanPrice();
        double slip = ThreadLocalRandom.current().nextDouble(-1, 1);
        return base.add(MAX_SLIPPAGE.multiply(BigDecimal.valueOf(slip)))
                .setScale(4, RoundingMode.HALF_UP);
    }

    /** MARKET orders always execute; LIMIT orders only when the price is at their limit or better. */
    private boolean isMarketable(Order order, BigDecimal price) {
        if (order.getOrderType() == OrderType.MARKET) {
            return true;
        }
        BigDecimal limit = order.getLimitPrice();
        return order.getSide() == OrderSide.BUY
                ? price.compareTo(limit) <= 0
                : price.compareTo(limit) >= 0;
    }
}
