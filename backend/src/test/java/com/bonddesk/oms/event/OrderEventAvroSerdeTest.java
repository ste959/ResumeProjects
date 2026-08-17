package com.bonddesk.oms.event;

import com.bonddesk.contracts.OrderEventRecord;
import com.bonddesk.oms.domain.OrderStatus;
import io.confluent.kafka.serializers.KafkaAvroDeserializer;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The full producer serializer to consumer deserializer round-trip, through a real Confluent Avro codec
 * and an in-memory ({@code mock://}) Schema Registry — so it exercises schema registration and the
 * schema-id-prefixed wire format without a broker or a running registry. Proves a domain OrderEvent
 * survives the trip with its enums, exact decimals, and microsecond timestamp intact.
 */
class OrderEventAvroSerdeTest {

    // Same scope on both ends → they share one in-memory registry (Confluent MockSchemaRegistry).
    private static final String REGISTRY = "mock://order-events-serde-test";

    @Test
    void roundTripsADomainEventThroughAvroAndTheRegistry() {
        OrderEventAvroSerializer serializer = new OrderEventAvroSerializer();
        serializer.configure(Map.of("schema.registry.url", REGISTRY), false);

        KafkaAvroDeserializer deserializer = new KafkaAvroDeserializer();
        deserializer.configure(Map.of(
                "schema.registry.url", REGISTRY,
                "specific.avro.reader", "true"), false);

        OrderEvent event = new OrderEvent(
                OrderEvent.Type.ORDER_FILLED, "O-1", "912828XG8", "DESK-A",
                OrderStatus.FILLED, new BigDecimal("1000000"), new BigDecimal("500000.00"),
                Instant.parse("2026-01-01T00:00:00.123456Z"));

        byte[] wire = serializer.serialize("order-events", event);
        Object decoded = deserializer.deserialize("order-events", wire);

        assertThat(decoded).isInstanceOf(OrderEventRecord.class);
        OrderEventRecord r = (OrderEventRecord) decoded;
        assertThat(r.getType().name()).isEqualTo("ORDER_FILLED");
        assertThat(r.getOrderRef()).isEqualTo("O-1");
        assertThat(r.getCusip()).isEqualTo("912828XG8");
        assertThat(r.getPortfolio()).isEqualTo("DESK-A");
        assertThat(r.getStatus().name()).isEqualTo("FILLED");
        assertThat(r.getQuantity()).isEqualByComparingTo("1000000");
        assertThat(r.getFilledQuantity()).isEqualByComparingTo("500000");
        assertThat(r.getOccurredAt()).isEqualTo(Instant.parse("2026-01-01T00:00:00.123456Z"));
    }

    @Test
    void serializingNullYieldsNull() {
        OrderEventAvroSerializer serializer = new OrderEventAvroSerializer();
        serializer.configure(Map.of("schema.registry.url", REGISTRY), false);
        assertThat(serializer.serialize("order-events", null)).isNull();
    }
}
