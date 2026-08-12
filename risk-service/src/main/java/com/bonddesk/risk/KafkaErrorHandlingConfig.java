package com.bonddesk.risk;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

/**
 * Consumer resilience for the order-event stream. Spring Boot auto-applies a single
 * {@link DefaultErrorHandler} bean to the listener container, so this is all that's needed to turn a
 * poison message from "wedges the consumer forever" into "retried a few times, then parked on a
 * dead-letter topic while the stream keeps flowing."
 *
 * <ul>
 *   <li>Transient processing failures: retried 3× at 2s (the {@link FixedBackOff}).</li>
 *   <li>Deserialization failures (a malformed record): {@code DefaultErrorHandler} treats these as
 *       non-retryable by default and routes them straight to the DLT — retrying an unparseable record
 *       would never succeed.</li>
 *   <li>After retries are exhausted, the {@link DeadLetterPublishingRecoverer} republishes the raw
 *       record to {@code order-events.DLT} and the container commits past it.</li>
 * </ul>
 */
@Configuration
public class KafkaErrorHandlingConfig {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<?, ?> deadLetterTemplate) {
        DeadLetterPublishingRecoverer recoverer = new DeadLetterPublishingRecoverer(deadLetterTemplate);
        return new DefaultErrorHandler(recoverer, new FixedBackOff(2000L, 3));
    }
}
