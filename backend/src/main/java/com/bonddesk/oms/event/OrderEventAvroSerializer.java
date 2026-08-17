package com.bonddesk.oms.event;

import io.confluent.kafka.serializers.KafkaAvroSerializer;
import org.apache.kafka.common.serialization.Serializer;

import java.util.Map;

/**
 * Kafka value serializer for order events: maps the domain {@link OrderEvent} to its Avro
 * {@link com.bonddesk.contracts.OrderEventRecord} and delegates to Confluent's {@link KafkaAvroSerializer},
 * which registers the schema with the Schema Registry (subject {@code order-events-value}) and prefixes
 * the payload with the registered schema id. Because the mapping lives here, the outbox relay keeps
 * sending plain domain events and knows nothing about Avro or the registry.
 */
public class OrderEventAvroSerializer implements Serializer<OrderEvent> {

    private final KafkaAvroSerializer inner = new KafkaAvroSerializer();

    @Override
    public void configure(Map<String, ?> configs, boolean isKey) {
        inner.configure(configs, isKey);   // reads schema.registry.url from the producer properties
    }

    @Override
    public byte[] serialize(String topic, OrderEvent data) {
        return data == null ? null : inner.serialize(topic, OrderEventAvroMapper.toAvro(data));
    }

    @Override
    public void close() {
        inner.close();
    }
}
