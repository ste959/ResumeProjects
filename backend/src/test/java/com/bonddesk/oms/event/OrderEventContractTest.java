package com.bonddesk.oms.event;

import com.bonddesk.oms.domain.OrderStatus;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Producer-side structural check for the {@code order-events} event. The enforced wire contract is now
 * the Avro schema ({@code schemas/avro/order-event.avsc}), whose compatibility the Schema Registry
 * guarantees (see {@code OrderEventSchemaCompatibilityTest} + ADR-0009); this test is the lighter
 * companion that keeps the producer's {@code OrderEvent} field/enum names in step with the human-readable
 * field reference in {@code /contracts/order-event.json}, so a rename shows up here too.
 */
class OrderEventContractTest {

    private final ObjectMapper mapper = new ObjectMapper().registerModule(new JavaTimeModule());

    private JsonNode contract() throws Exception {
        for (Path p : List.of(Path.of("..", "contracts", "order-event.json"),
                              Path.of("contracts", "order-event.json"))) {
            if (Files.exists(p)) {
                return mapper.readTree(Files.readString(p));
            }
        }
        throw new IllegalStateException("contracts/order-event.json not found from " + Path.of(".").toAbsolutePath());
    }

    private Set<String> stringSet(JsonNode array) {
        return StreamSupport.stream(array.spliterator(), false).map(JsonNode::asText).collect(Collectors.toSet());
    }

    @Test
    void eventTypeEnumMatchesTheContract() throws Exception {
        Set<String> declared = Arrays.stream(OrderEvent.Type.values()).map(Enum::name).collect(Collectors.toSet());
        assertThat(declared).isEqualTo(stringSet(contract().get("types")));   // add/rename/remove → fails
    }

    @Test
    void orderStatusEnumMatchesTheContract() throws Exception {
        Set<String> declared = Arrays.stream(OrderStatus.values()).map(Enum::name).collect(Collectors.toSet());
        assertThat(declared).isEqualTo(stringSet(contract().get("statuses")));
    }

    @Test
    void serializedFieldsMatchTheContract() throws Exception {
        OrderEvent event = new OrderEvent(OrderEvent.Type.ORDER_FILLED, "O-123", "912828XG8", "DESK-A",
                OrderStatus.FILLED, BigDecimal.valueOf(1000), BigDecimal.valueOf(1000),
                Instant.parse("2024-01-01T00:00:00Z"));
        JsonNode json = mapper.valueToTree(event);
        Set<String> emitted = StreamSupport.stream(
                ((Iterable<String>) json::fieldNames).spliterator(), false).collect(Collectors.toSet());
        assertThat(emitted).isEqualTo(stringSet(contract().get("fields")));
    }
}
