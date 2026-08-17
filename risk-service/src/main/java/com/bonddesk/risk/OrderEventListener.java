package com.bonddesk.risk;

import com.bonddesk.contracts.OrderEventRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

/**
 * Subscribes to the OMS order-event topic and feeds each event into the aggregator. Records arrive as the
 * Avro {@link OrderEventRecord} (the shared schema), which the deserializer resolves against the registry;
 * they are mapped to the risk service's own {@link OrderEvent} before aggregation.
 */
@Component
public class OrderEventListener {

    private static final Logger log = LoggerFactory.getLogger(OrderEventListener.class);

    private final RiskAggregator aggregator;

    public OrderEventListener(RiskAggregator aggregator) {
        this.aggregator = aggregator;
    }

    @KafkaListener(topics = "${oms.kafka.topic:order-events}", groupId = "${spring.kafka.consumer.group-id:risk-service}")
    public void onOrderEvent(OrderEventRecord record) {
        OrderEvent event = OrderEventAvroMapper.fromAvro(record);
        log.debug("Consumed {} for order {} ({})", event.type(), event.orderRef(), event.status());
        aggregator.record(event);
    }
}
