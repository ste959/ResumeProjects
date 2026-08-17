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
 * Producer half of the consumer-driven contract for the {@code order-events} topic. The risk service
 * hand-maintains its own {@code OrderEvent} coupled to this producer only by the JSON contract in
 * {@code /contracts/order-event.json}; this test fails if the producer drifts from it — so renaming an
 * enum value or a field can't silently break downstream risk aggregation.
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
