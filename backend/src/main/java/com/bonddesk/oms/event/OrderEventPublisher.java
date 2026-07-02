package com.bonddesk.oms.event;

/**
 * Publishes order lifecycle events. Abstracting this behind an interface lets the OMS
 * run standalone (with a logging publisher) in dev/test, and switch to Kafka in
 * cloud deployments purely by configuration — no service-code changes.
 */
public interface OrderEventPublisher {
    void publish(OrderEvent event);
}
