package com.bonddesk.oms.event;

import com.bonddesk.oms.domain.OutboxEvent;
import com.bonddesk.oms.repository.OutboxEventRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * The Kafka-path {@link OrderEventPublisher}. Instead of sending to the broker directly (a dual write
 * against the DB that can produce phantom or lost events), it appends the event to the transactional
 * {@code outbox_event} table. Because {@code OrderService} calls this from inside its {@code @Transactional}
 * write, the event row and the order change commit — or roll back — together. {@link OutboxRelay}
 * asynchronously drains the table to Kafka.
 *
 * <p>Active only when {@code oms.kafka.enabled=true}; otherwise {@link LoggingOrderEventPublisher} runs.
 */
@Component("outboxOrderEventPublisher")
@ConditionalOnProperty(prefix = "oms.kafka", name = "enabled", havingValue = "true")
public class OutboxOrderEventPublisher implements OrderEventPublisher {

    private final OutboxEventRepository outbox;
    private final ObjectMapper json;
    private final String topic;

    public OutboxOrderEventPublisher(OutboxEventRepository outbox, ObjectMapper json,
                                     @Value("${oms.kafka.topic:order-events}") String topic) {
        this.outbox = outbox;
        this.json = json;
        this.topic = topic;
    }

    @Override
    public void publish(OrderEvent event) {
        String payload;
        try {
            payload = json.writeValueAsString(event);
        } catch (JsonProcessingException e) {
            // An event we can't serialize is a programming error, not a transient fault — fail the
            // enclosing transaction loudly rather than silently committing the order without its event.
            throw new IllegalStateException("Failed to serialize order event for the outbox", e);
        }
        // No explicit @Transactional: this runs inside the caller's transaction (OrderService), which
        // is exactly the point — the outbox row is atomic with the order write.
        outbox.save(new OutboxEvent(event.orderRef(), event.type().name(), topic, payload, event.occurredAt()));
    }
}
