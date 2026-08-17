package com.bonddesk.risk;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Consumer half of the {@code order-events} contract. The risk service deserializes into its own
 * {@code OrderEvent}; this test proves it accepts everything the shared contract
 * ({@code /contracts/order-event.json}) says the producer emits — the canonical sample and every
 * declared type/status — so a producer change that fits the contract can't surprise the consumer, and a
 * consumer change that breaks the contract fails here.
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
        throw new IllegalStateException("contracts/order-event.json not found");
    }

    @Test
    void deserializesTheCanonicalSample() throws Exception {
        OrderEvent event = mapper.treeToValue(contract().get("sample"), OrderEvent.class);
        assertThat(event.type()).isEqualTo("ORDER_FILLED");
        assertThat(event.orderRef()).isEqualTo("O-123");
        assertThat(event.status()).isEqualTo("FILLED");
        assertThat(event.filledQuantity()).isNotNull();
        assertThat(event.occurredAt()).isNotNull();
    }

    @Test
    void acceptsEveryDeclaredTypeAndStatus() throws Exception {
        JsonNode c = contract();
        ObjectNode base = (ObjectNode) c.get("sample").deepCopy();
        for (JsonNode type : c.get("types")) {
            OrderEvent e = mapper.treeToValue(base.deepCopy().put("type", type.asText()), OrderEvent.class);
            assertThat(e.type()).isEqualTo(type.asText());
        }
        for (JsonNode status : c.get("statuses")) {
            OrderEvent e = mapper.treeToValue(base.deepCopy().put("status", status.asText()), OrderEvent.class);
            assertThat(e.status()).isEqualTo(status.asText());
        }
    }

    @Test
    void aggregatorCountsAContractEvent() throws Exception {
        OrderEvent event = mapper.treeToValue(contract().get("sample"), OrderEvent.class);
        RiskAggregator aggregator = new RiskAggregator();
        aggregator.record(event);
        assertThat(aggregator.summary().ordersByStatus()).containsKey("FILLED");
    }
}
