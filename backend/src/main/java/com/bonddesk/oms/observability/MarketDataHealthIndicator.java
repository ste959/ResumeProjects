package com.bonddesk.oms.observability;

import com.bonddesk.oms.market.MarketDataService;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;

/**
 * Custom health for the live Coinbase market-data feed ({@code marketDataFeed} under
 * {@code /actuator/health}). UP while trades are flowing; DOWN if the feed was live but has gone
 * stale. When it has never delivered (feed disabled/offline — e.g. tests) it reports UP-and-idle so
 * an optional feed doesn't drag the whole app to DOWN.
 */
@Component("marketDataFeed")
public class MarketDataHealthIndicator implements HealthIndicator {

    private static final long STALE_SECONDS = 60;

    private final MarketDataService marketData;

    public MarketDataHealthIndicator(MarketDataService marketData) {
        this.marketData = marketData;
    }

    @Override
    public Health health() {
        Instant last = marketData.lastUpdate();
        if (last == null) {
            return Health.up().withDetail("feed", "idle — no data yet (feed disabled or connecting)").build();
        }
        long secs = Duration.between(last, Instant.now()).getSeconds();
        return (secs <= STALE_SECONDS ? Health.up() : Health.down())
                .withDetail("lastUpdate", last.toString())
                .withDetail("secondsSinceUpdate", secs)
                .build();
    }
}
