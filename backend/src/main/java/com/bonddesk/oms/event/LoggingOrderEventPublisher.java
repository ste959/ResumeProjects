package com.bonddesk.oms.event;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Default event publisher used when no messaging broker is configured. It simply logs
 * events, which keeps the OMS fully runnable on a laptop with nothing but a JDK.
 * The Kafka-backed publisher replaces it when {@code oms.kafka.enabled=true}.
 */
@Component
@ConditionalOnProperty(prefix = "oms.kafka", name = "enabled", havingValue = "false", matchIfMissing = true)
public class LoggingOrderEventPublisher implements OrderEventPublisher {

    private static final Logger log = LoggerFactory.getLogger("order-events");

    @Override
    public void publish(OrderEvent event) {
        log.info("[{}] order={} {} {} status={} filled={}/{}",
                event.type(), event.orderRef(), event.portfolio(), event.cusip(),
                event.status(), event.filledQuantity(), event.quantity());
    }
}
