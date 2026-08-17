package com.bonddesk.oms.event;

import com.bonddesk.contracts.EventType;
import com.bonddesk.contracts.OrderEventRecord;
import com.bonddesk.contracts.OrderStatus;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Converts the OMS's internal {@link OrderEvent} into the Avro {@link OrderEventRecord} that goes on the
 * wire. Keeping the domain event and the wire schema as separate types is deliberate: the internal model
 * can change freely, while the wire contract only ever changes through the schema (and the registry's
 * compatibility check). Enums map by name — the schema's symbols and the domain enums are kept in step.
 */
final class OrderEventAvroMapper {

    private OrderEventAvroMapper() {
    }

    static OrderEventRecord toAvro(OrderEvent e) {
        return OrderEventRecord.newBuilder()
                .setType(EventType.valueOf(e.type().name()))
                .setOrderRef(e.orderRef())
                .setCusip(e.cusip())
                .setPortfolio(e.portfolio())
                .setStatus(OrderStatus.valueOf(e.status().name()))
                .setQuantity(scaled(e.quantity()))
                .setFilledQuantity(scaled(e.filledQuantity()))
                .setOccurredAt(e.occurredAt())
                .build();
    }

    /** The Avro decimal is declared scale=2, so normalise before encoding (Avro rejects a scale mismatch). */
    private static BigDecimal scaled(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_UP);
    }
}
