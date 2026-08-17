package com.bonddesk.oms.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * A durable outbox row. Order-lifecycle events are written here <b>in the same database
 * transaction</b> as the order change, so the event and the state it describes commit atomically —
 * eliminating the dual-write hole where a fire-and-forget Kafka send could publish a phantom event
 * (on rollback) or silently drop one (on broker outage). A separate relay drains unpublished rows to
 * the broker and stamps {@link #publishedAt}. Delivery is at-least-once; the consumer is idempotent
 * (latest-event-per-key), so a resent row is harmless.
 */
@Entity
@Table(name = "outbox_event",
       indexes = @Index(name = "ix_outbox_pending", columnList = "published_at, dead_lettered_at, id"))
public class OutboxEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** The aggregate this event is about (the order reference) — also the Kafka message key. */
    @Column(name = "aggregate_id", nullable = false)
    private String aggregateId;

    @Column(name = "event_type", nullable = false, length = 64)
    private String eventType;

    @Column(nullable = false)
    private String topic;

    /** Serialized {@code OrderEvent} JSON — the immutable payload as of publish time. */
    @Column(name = "payload", nullable = false, columnDefinition = "text")
    private String payload;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    /** Null until the relay has confirmed the broker acked this row. */
    @Column(name = "published_at")
    private Instant publishedAt;

    @Column(nullable = false)
    private int attempts;

    /** Set when the relay gives up on a row (unparseable payload, or send failed past the retry cap),
     *  so a poison row is parked instead of blocking every later event behind it forever. */
    @Column(name = "dead_lettered_at")
    private Instant deadLetteredAt;

    @Column(name = "dead_letter_reason", length = 512)
    private String deadLetterReason;

    protected OutboxEvent() { } // for JPA

    public OutboxEvent(String aggregateId, String eventType, String topic, String payload, Instant createdAt) {
        this.aggregateId = aggregateId;
        this.eventType = eventType;
        this.topic = topic;
        this.payload = payload;
        this.createdAt = createdAt;
    }

    public void markPublished(Instant when) {
        this.publishedAt = when;
    }

    public void recordFailedAttempt() {
        this.attempts++;
    }

    public void markDeadLettered(Instant when, String reason) {
        this.deadLetteredAt = when;
        this.deadLetterReason = reason;
    }

    public Long getId() { return id; }
    public String getAggregateId() { return aggregateId; }
    public String getEventType() { return eventType; }
    public String getTopic() { return topic; }
    public String getPayload() { return payload; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getPublishedAt() { return publishedAt; }
    public int getAttempts() { return attempts; }
    public Instant getDeadLetteredAt() { return deadLetteredAt; }
    public String getDeadLetterReason() { return deadLetterReason; }
}
