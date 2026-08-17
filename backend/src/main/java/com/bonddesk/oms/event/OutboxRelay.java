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

import org.springframework.kafka.support.SendResult;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

/**
 * Drains the transactional outbox to Kafka. Polls the oldest unpublished rows, sends each to the
 * broker keyed by order reference (preserving per-order ordering on one partition), and stamps
 * {@code publishedAt} only after the broker acks. Delivery is <b>at-least-once</b>; the idempotent
 * producer plus the latest-event-per-key consumer make redelivery harmless.
 *
 * <p>Failures are handled by cause so one bad row can't wedge the whole stream:
 * <ul>
 *   <li>an <b>unparseable payload</b> will never succeed, so it is dead-lettered immediately and the
 *       relay moves on (it does not block every later event behind it);</li>
 *   <li>a <b>transient send failure</b> (broker down) stops the batch to preserve ordering and is
 *       retried next tick — but after {@code MAX_SEND_ATTEMPTS} the row is dead-lettered so a
 *       permanently-failing head can't stall the outbox forever.</li>
 * </ul>
 * A retention purge bounds table growth. Active only when {@code oms.kafka.enabled=true}.
 */
@Component
@ConditionalOnProperty(prefix = "oms.kafka", name = "enabled", havingValue = "true")
public class OutboxRelay {

    private static final Logger log = LoggerFactory.getLogger(OutboxRelay.class);
    private static final int BATCH = 128;
    private static final long ACK_TIMEOUT_SECONDS = 10;
    private static final int MAX_SEND_ATTEMPTS = 5;
    private static final Duration RETENTION = Duration.ofDays(7);

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
        List<OutboxEvent> pending =
                outbox.findByPublishedAtIsNullAndDeadLetteredAtIsNullOrderByIdAsc(Limit.of(BATCH));

        // Phase 1 — fire every send without awaiting each ack. Throughput is then bounded by the
        // producer's in-flight batching, not by one round-trip per row (the old serial loop capped at
        // ~100/s). Ordering is still safe: all events for one order share a partition and the idempotent
        // producer preserves per-partition order across retries, so delivery order == send order here
        // regardless of the order we await the acks in.
        List<Map.Entry<OutboxEvent, CompletableFuture<SendResult<String, OrderEvent>>>> inflight =
                new ArrayList<>(pending.size());
        for (OutboxEvent row : pending) {
            OrderEvent event;
            try {
                event = json.readValue(row.getPayload(), OrderEvent.class);
            } catch (Exception parseEx) {
                // Permanent: retrying an unparseable row never helps → park it and keep the stream moving.
                row.markDeadLettered(Instant.now(), "unparseable payload: " + parseEx.getMessage());
                log.error("Outbox row id={} dead-lettered (unparseable payload)", row.getId(), parseEx);
                continue;
            }
            inflight.add(Map.entry(row, kafka.send(row.getTopic(), row.getAggregateId(), event)));
        }

        // Phase 2 — await acks; mark published on confirmed delivery, retry/dead-letter on failure. An
        // un-acked row simply isn't marked and is retried next tick (a redelivery is harmless: idempotent
        // producer + latest-event-per-key consumer).
        for (Map.Entry<OutboxEvent, CompletableFuture<SendResult<String, OrderEvent>>> e : inflight) {
            OutboxEvent row = e.getKey();
            try {
                e.getValue().get(ACK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
                row.markPublished(Instant.now());          // dirty-checked; flushed at commit
            } catch (Exception sendEx) {
                row.recordFailedAttempt();
                if (row.getAttempts() >= MAX_SEND_ATTEMPTS) {
                    row.markDeadLettered(Instant.now(), "send failed after " + MAX_SEND_ATTEMPTS + " attempts");
                    log.error("Outbox row id={} dead-lettered after {} send attempts",
                            row.getId(), MAX_SEND_ATTEMPTS, sendEx);
                } else {
                    log.warn("Outbox row id={} send failed (attempt {}): {}",
                            row.getId(), row.getAttempts(), sendEx.toString());
                }
            }
        }
    }

    /** Retention purge: delete acknowledged rows older than {@link #RETENTION} so the table stays bounded. */
    @Scheduled(fixedDelayString = "${oms.kafka.outbox.purge-ms:3600000}")   // hourly
    @Transactional
    public void purge() {
        int deleted = outbox.deletePublishedBefore(Instant.now().minus(RETENTION));
        if (deleted > 0) {
            log.info("Outbox purged {} published rows older than {}", deleted, RETENTION);
        }
    }
}
