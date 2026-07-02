package com.bonddesk.risk;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

/** Subscribes to the OMS order-event topic and feeds each event into the aggregator. */
@Component
public class OrderEventListener {

    private static final Logger log = LoggerFactory.getLogger(OrderEventListener.class);

    private final RiskAggregator aggregator;

    public OrderEventListener(RiskAggregator aggregator) {
        this.aggregator = aggregator;
    }

    @KafkaListener(topics = "${oms.kafka.topic:order-events}", groupId = "${spring.kafka.consumer.group-id:risk-service}")
    public void onOrderEvent(OrderEvent event) {
        log.debug("Consumed {} for order {} ({})", event.type(), event.orderRef(), event.status());
        aggregator.record(event);
    }
}
