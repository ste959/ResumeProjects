package com.bonddesk.risk;

import com.bonddesk.contracts.EventType;
import com.bonddesk.contracts.OrderEventRecord;
import com.bonddesk.contracts.OrderStatus;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Consumer half of the {@code order-events} contract. The wire format is now the shared Avro schema
 * ({@code src/main/avro/order-event.avsc}); the deserializer hands the listener an {@link OrderEventRecord}
 * and {@link OrderEventAvroMapper} turns it into the risk service's own {@link OrderEvent}. This proves
 * that mapping handles every event type and status the schema can carry, and that a mapped event
 * aggregates — so a registry-accepted producer change can't surprise the consumer, and a break in the
 * mapper fails here. (Schema compatibility itself is enforced by the registry and the OMS's
 * OrderEventSchemaCompatibilityTest.)
 */
class OrderEventContractTest {

    @Test
    void mapsEveryEventTypeTheSchemaCanCarry() {
        for (EventType type : EventType.values()) {
            OrderEvent event = OrderEventAvroMapper.fromAvro(sample(type, OrderStatus.NEW));
            assertThat(event.type()).isEqualTo(type.name());
        }
    }

    @Test
    void mapsEveryStatusTheSchemaCanCarry() {
        for (OrderStatus status : OrderStatus.values()) {
            OrderEvent event = OrderEventAvroMapper.fromAvro(sample(EventType.ORDER_CREATED, status));
            assertThat(event.status()).isEqualTo(status.name());
        }
    }

    @Test
    void mapsAllFieldsOfACanonicalEvent() {
        OrderEvent event = OrderEventAvroMapper.fromAvro(sample(EventType.ORDER_FILLED, OrderStatus.FILLED));
        assertThat(event.type()).isEqualTo("ORDER_FILLED");
        assertThat(event.orderRef()).isEqualTo("O-123");
        assertThat(event.cusip()).isEqualTo("912828XG8");
        assertThat(event.portfolio()).isEqualTo("DESK-A");
        assertThat(event.status()).isEqualTo("FILLED");
        assertThat(event.quantity()).isEqualByComparingTo("1000");
        assertThat(event.filledQuantity()).isEqualByComparingTo("1000");
        assertThat(event.occurredAt()).isEqualTo(Instant.parse("2026-01-01T00:00:00Z"));
    }

    @Test
    void aggregatorCountsAMappedEvent() {
        OrderEvent event = OrderEventAvroMapper.fromAvro(sample(EventType.ORDER_FILLED, OrderStatus.FILLED));
        RiskAggregator aggregator = new RiskAggregator();
        aggregator.record(event);
        assertThat(aggregator.summary().ordersByStatus()).containsKey("FILLED");
    }

    private static OrderEventRecord sample(EventType type, OrderStatus status) {
        return OrderEventRecord.newBuilder()
                .setType(type)
                .setOrderRef("O-123")
                .setCusip("912828XG8")
                .setPortfolio("DESK-A")
                .setStatus(status)
                .setQuantity(new BigDecimal("1000.00"))
                .setFilledQuantity(new BigDecimal("1000.00"))
                .setOccurredAt(Instant.parse("2026-01-01T00:00:00Z"))
                .build();
    }
}
