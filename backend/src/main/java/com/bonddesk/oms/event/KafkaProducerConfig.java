package com.bonddesk.oms.event;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

import java.util.HashMap;
import java.util.Map;

/**
 * Wires an Avro-publishing {@link KafkaTemplate} for order events, registered against a Confluent Schema
 * Registry. Only active when {@code oms.kafka.enabled=true}, so the OMS still boots with no broker in
 * dev/test.
 *
 * <p>The wire format is the {@code order-event.avsc} schema, shared with the risk consumer; the registry
 * enforces BACKWARD compatibility so an incompatible change is rejected before it can reach the topic.
 * The domain-to-Avro mapping lives in {@link OrderEventAvroSerializer}, so the rest of the OMS keeps
 * dealing in plain {@link OrderEvent}s.
 */
@Configuration
@ConditionalOnProperty(prefix = "oms.kafka", name = "enabled", havingValue = "true")
public class KafkaProducerConfig {

    @Bean
    public ProducerFactory<String, OrderEvent> orderEventProducerFactory(
            @Value("${oms.kafka.bootstrap-servers:localhost:9092}") String bootstrapServers,
            @Value("${oms.kafka.schema-registry-url:http://localhost:8081}") String schemaRegistryUrl) {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, OrderEventAvroSerializer.class);
        props.put("schema.registry.url", schemaRegistryUrl);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        // Idempotent producer: a retried send is de-duplicated by the broker (producer-id + sequence)
        // and ordering is preserved per partition. Since every event is keyed by orderRef, all events
        // for one order land on the same partition in order — so a transient retry can't duplicate or
        // reorder an order's lifecycle. (Requires acks=all, set above.)
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION, 5);
        props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
        // Batching: a small linger lets the outbox relay's pipelined sends coalesce into fewer, larger,
        // compressed requests — real throughput once the relay fires a batch without awaiting each ack.
        props.put(ProducerConfig.LINGER_MS_CONFIG, 10);
        props.put(ProducerConfig.BATCH_SIZE_CONFIG, 32 * 1024);
        props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "lz4");
        return new DefaultKafkaProducerFactory<>(props);
    }

    @Bean
    public KafkaTemplate<String, OrderEvent> orderEventKafkaTemplate(
            ProducerFactory<String, OrderEvent> factory) {
        KafkaTemplate<String, OrderEvent> template = new KafkaTemplate<>(factory);
        // Emit a producer span per send and inject the W3C trace context into the record headers, so a
        // consumer that continues the observation ties its processing span to the request that produced
        // the event — one trace spanning the OMS, the topic, and the risk service.
        template.setObservationEnabled(true);
        return template;
    }
}
