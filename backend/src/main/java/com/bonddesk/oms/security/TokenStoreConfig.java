package com.bonddesk.oms.security;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * Selects the {@link TokenStore} at startup: Redis-backed when {@code oms.redis.enabled=true} (shared
 * across instances), otherwise in-memory (single node, the default) — the same switch the idempotency
 * store uses, so the app boots with or without Redis.
 */
@Configuration
public class TokenStoreConfig {

    @Bean
    @ConditionalOnProperty(prefix = "oms.redis", name = "enabled", havingValue = "true")
    public TokenStore redisTokenStore(StringRedisTemplate redis) {
        return new RedisTokenStore(redis);
    }

    @Bean
    @ConditionalOnProperty(prefix = "oms.redis", name = "enabled", havingValue = "false", matchIfMissing = true)
    public TokenStore inMemoryTokenStore() {
        return new InMemoryTokenStore();
    }
}
