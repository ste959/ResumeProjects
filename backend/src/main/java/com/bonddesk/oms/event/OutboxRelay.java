package com.bonddesk.oms.event;

import com.bonddesk.oms.domain.OutboxEvent;
import com.bonddesk.oms.repository.OutboxEventRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.Limit;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Drains the transactional outbox to Kafka. Polls the oldest unpublished rows, sends each to the
 * broker keyed by order reference (preserving per-order ordering on one partition), and stamps
 * {@code publishedAt} only after the broker acks. A send failure (broker down) leaves the row
 * unpublished for the next tick — so delivery is <b>at-least-once</b>; the idempotent producer plus
 * the latest-event-per-key consumer make redelivery harmless.
 *
 * <p>Active only when {@code oms.kafka.enabled=true} (paired with {@link OutboxOrderEventPublisher}).
 */
@Component
@ConditionalOnProperty(prefix = "oms.kafka", name = "enabled", havingValue = "true")
public class OutboxRelay {

    private static final Logger log = LoggerFactory.getLogger(OutboxRelay.class);
    private static final int BATCH = 128;
    private static final long ACK_TIMEOUT_SECONDS = 10;

    private final OutboxEventRepository outbox;
    private final KafkaTemplate<String, OrderEvent> kafka;
    private final ObjectMapper json;

    public OutboxRelay(OutboxEventRepository outbox, KafkaTemplate<String, OrderEvent> kafka, ObjectMapper json) {
        this.outbox = outbox;
        this.kafka = kafka;
        this.json = json;
    }

    @Scheduled(fixedDelayString = "${oms.kafka.outbox.poll-ms:1000}")
    @Transactional
    public void drain() {
        List<OutboxEvent> pending = outbox.findByPublishedAtIsNullOrderByIdAsc(Limit.of(BATCH));
        for (OutboxEvent row : pending) {
            try {
                OrderEvent event = json.readValue(row.getPayload(), OrderEvent.class);
                // Block on the broker ack so we only mark published on confirmed delivery.
                kafka.send(row.getTopic(), row.getAggregateId(), event)
                        .get(ACK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
                row.markPublished(Instant.now());          // dirty-checked; flushed at commit
            } catch (Exception ex) {
                // Broker hiccup or bad payload: record the attempt and stop this batch. The row stays
                // unpublished and is retried next tick (ordering within an aggregate is preserved
                // because we stop rather than skip ahead).
                row.recordFailedAttempt();
                log.warn("Outbox relay stalled at id={} (attempt {}): {}",
                        row.getId(), row.getAttempts(), ex.toString());
                break;
            }
        }
    }
}
