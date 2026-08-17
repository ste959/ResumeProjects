package com.bonddesk.risk;

import com.bonddesk.contracts.OrderEventRecord;

/**
 * Maps the Avro {@link OrderEventRecord} coming off the topic into the risk service's own
 * {@link OrderEvent}. The risk service keeps its own domain view (only the fields it needs, as plain
 * strings) rather than aggregating over the generated type directly — the schema is the shared contract,
 * but each service still owns how it models what it consumes.
 */
final class OrderEventAvroMapper {

    private OrderEventAvroMapper() {
    }

    static OrderEvent fromAvro(OrderEventRecord r) {
        return new OrderEvent(
                r.getType().name(),
                r.getOrderRef(),
                r.getCusip(),
                r.getPortfolio(),
                r.getStatus().name(),
                r.getQuantity(),
                r.getFilledQuantity(),
                r.getOccurredAt()
        );
    }
}
