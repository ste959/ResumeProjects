package com.bonddesk.risk;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * The risk service's own view of an order event. It intentionally does not share a
 * class with the OMS — the two services are coupled only by the shared Avro schema on the
 * topic (each maps the wire {@code OrderEventRecord} into its own model), which is what keeps
 * them independently deployable.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderEvent(
        String type,
        String orderRef,
        String cusip,
        String portfolio,
        String status,
        BigDecimal quantity,
        BigDecimal filledQuantity,
        Instant occurredAt
) {
}
