package com.bonddesk.oms.event;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

import java.util.HashMap;
import java.util.Map;

/**
 * Wires a JSON-publishing {@link KafkaTemplate} for order events. Only active when
 * {@code oms.kafka.enabled=true}, so the OMS still boots with no broker in dev/test.
 *
 * <p>Type-info headers are switched off: the risk service deserialises into its own
 * {@code OrderEvent} class, so we keep the wire format a plain, portable JSON document
 * rather than coupling consumers to this module's package names.
 */
@Configuration
@ConditionalOnProperty(prefix = "oms.kafka", name = "enabled", havingValue = "true")
public class KafkaProducerConfig {

    @Bean
    public ProducerFactory<String, OrderEvent> orderEventProducerFactory(
            @org.springframework.beans.factory.annotation.Value("${oms.kafka.bootstrap-servers:localhost:9092}")
            String bootstrapServers) {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);
        props.put(JsonSerializer.ADD_TYPE_INFO_HEADERS, false);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        return new DefaultKafkaProducerFactory<>(props);
    }

    @Bean
    public KafkaTemplate<String, OrderEvent> orderEventKafkaTemplate(
            ProducerFactory<String, OrderEvent> factory) {
        return new KafkaTemplate<>(factory);
    }
}
