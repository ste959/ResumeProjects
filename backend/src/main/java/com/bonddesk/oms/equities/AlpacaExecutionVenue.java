package com.bonddesk.oms.equities;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.equities.AlpacaBrokerClient.AlpacaOrder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Routes equity orders to the Alpaca (paper) broker. This is the equities analogue of the
 * crypto matching engine: instead of matching in-process, it hands the order to a real
 * external venue. Fills come back asynchronously and are booked by {@link AlpacaReconciler},
 * so this class only submits and cancels.
 */
@Component
@ConditionalOnProperty(prefix = "oms.equities", name = "enabled", havingValue = "true", matchIfMissing = true)
public class AlpacaExecutionVenue {

    private static final Logger log = LoggerFactory.getLogger(AlpacaExecutionVenue.class);

    private final AlpacaProperties props;
    private final AlpacaBrokerClient broker;

    public AlpacaExecutionVenue(AlpacaProperties props, AlpacaBrokerClient broker) {
        this.props = props;
        this.broker = broker;
    }

    public void route(Order order) {
        if (!props.hasCredentials()) {
            log.warn("Equity order {} routed but Alpaca credentials are not set — cannot execute", order.getOrderRef());
            return;
        }
        try {
            AlpacaOrder ack = broker.submit(order);
            log.info("Routed equity order {} to Alpaca: {} {} {} -> broker id {} ({})",
                    order.getOrderRef(), order.getSide(), order.getQuantity(),
                    order.getSecurity().getTicker(), ack.id(), ack.status());
        } catch (RuntimeException e) {
            log.warn("Failed to route equity order {} to Alpaca: {}", order.getOrderRef(), e.getMessage());
        }
    }

    public void cancel(Order order) {
        if (!props.hasCredentials()) {
            return;
        }
        try {
            AlpacaOrder existing = broker.getByClientOrderId(order.getOrderRef());
            if (existing != null) {
                broker.cancel(existing.id());
                log.info("Requested Alpaca cancel of equity order {} (broker id {})",
                        order.getOrderRef(), existing.id());
            }
        } catch (RuntimeException e) {
            log.debug("Alpaca cancel of {} failed: {}", order.getOrderRef(), e.getMessage());
        }
    }
}
