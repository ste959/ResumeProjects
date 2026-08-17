package com.bonddesk.oms.idempotency;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;

/**
 * Selects the idempotency store at startup: the Redis-backed store when {@code oms.redis.enabled=true}
 * (a shared store across instances), otherwise the in-memory store (single-node, the default). Exactly
 * one {@link IdempotencyStore} bean is created, so the app boots with or without Redis.
 */
@Configuration
@EnableConfigurationProperties(IdempotencyProperties.class)
public class IdempotencyConfig {

    @Bean
    @ConditionalOnProperty(prefix = "oms.redis", name = "enabled", havingValue = "true")
    public IdempotencyStore redisIdempotencyStore(StringRedisTemplate redis, IdempotencyProperties props) {
        return new RedisIdempotencyStore(redis, props.getTtl());
    }

    @Bean
    @ConditionalOnProperty(prefix = "oms.redis", name = "enabled", havingValue = "false", matchIfMissing = true)
    public IdempotencyStore inMemoryIdempotencyStore(IdempotencyProperties props) {
        return new InMemoryIdempotencyStore(props.getTtl().toMillis());
    }
}
