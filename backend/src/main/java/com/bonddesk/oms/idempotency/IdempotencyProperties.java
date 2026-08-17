package com.bonddesk.oms.idempotency;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

/** Tunables for API idempotency. */
@ConfigurationProperties(prefix = "oms.idempotency")
public class IdempotencyProperties {

    /**
     * How long a key's outcome is retained so a retry can replay it. Long enough to cover a client's
     * realistic retry window (network blips, restarts), short enough that keys don't accumulate.
     */
    private Duration ttl = Duration.ofHours(24);

    public Duration getTtl() {
        return ttl;
    }

    public void setTtl(Duration ttl) {
        this.ttl = ttl;
    }
}
