package com.bonddesk.oms.observability;

import com.bonddesk.oms.exchange.ExchangeSimulation;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

/**
 * Custom health for the matching engine — surfaced as a component under {@code /actuator/health}
 * ({@code matchingEngine}). Reports DOWN if the book isn't live (no two-sided quote), which is the
 * signal an operator actually cares about: is the engine accepting and matching orders?
 */
@Component("matchingEngine")
public class MatchingEngineHealthIndicator implements HealthIndicator {

    private final ExchangeSimulation exchange;

    public MatchingEngineHealthIndicator(ExchangeSimulation exchange) {
        this.exchange = exchange;
    }

    @Override
    public Health health() {
        boolean live = exchange.twoSided();
        return (live ? Health.up() : Health.down())
                .withDetail("acceptingOrders", live)
                .withDetail("acceptedOrders", exchange.acceptedOrders())
                .withDetail("trades", exchange.trades())
                .withDetail("ordersPerSecond", Math.round(exchange.ordersPerSec()))
                .build();
    }
}
