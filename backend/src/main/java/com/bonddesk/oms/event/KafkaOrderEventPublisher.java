package com.bonddesk.oms.event;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/**
 * Publishes order lifecycle events to Kafka, keyed by order reference so all events for
 * one order land on the same partition and stay strictly ordered. Active only when
 * {@code oms.kafka.enabled=true}; otherwise {@link LoggingOrderEventPublisher} is used.
 */
@Component("kafkaOrderEventPublisher")
@ConditionalOnProperty(prefix = "oms.kafka", name = "enabled", havingValue = "true")
public class KafkaOrderEventPublisher implements OrderEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(KafkaOrderEventPublisher.class);

    private final KafkaTemplate<String, OrderEvent> kafka;
    private final String topic;

    public KafkaOrderEventPublisher(KafkaTemplate<String, OrderEvent> kafka,
                                    @Value("${oms.kafka.topic:order-events}") String topic) {
        this.kafka = kafka;
        this.topic = topic;
    }

    @Override
    public void publish(OrderEvent event) {
        kafka.send(topic, event.orderRef(), event).whenComplete((result, ex) -> {
            if (ex != null) {
                log.error("Failed to publish {} for order {}", event.type(), event.orderRef(), ex);
            } else {
                log.debug("Published {} for order {} to {}", event.type(), event.orderRef(), topic);
            }
        });
    }
}
