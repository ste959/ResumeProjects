package com.bonddesk.oms.observability;

import com.bonddesk.oms.exchange.ExchangeSimulation;
import io.micrometer.core.instrument.FunctionCounter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

/**
 * Publishes domain trading metrics from the matching engine to Micrometer, so they show up alongside
 * the JVM/HTTP metrics at {@code /actuator/prometheus} and on the Grafana dashboard. The gauges read
 * the engine's own counters lazily on each scrape — no hot-path instrumentation.
 */
@Component
public class ExchangeMetrics {

    public ExchangeMetrics(MeterRegistry registry, ExchangeSimulation exchange) {
        FunctionCounter.builder("exchange.orders.accepted", exchange, ExchangeSimulation::acceptedOrders)
                .description("Cumulative orders accepted by the matching engine")
                .register(registry);
        FunctionCounter.builder("exchange.trades", exchange, ExchangeSimulation::trades)
                .description("Cumulative trades matched by the engine")
                .register(registry);
        Gauge.builder("exchange.throughput.orders_per_second", exchange, ExchangeSimulation::ordersPerSec)
                .description("Recent matching-engine throughput")
                .register(registry);
        Gauge.builder("exchange.latency.p50.nanos", exchange, ExchangeSimulation::p50LatencyNanos)
                .description("Matching-engine submit latency, p50 (nanoseconds)")
                .register(registry);
        Gauge.builder("exchange.latency.p99.nanos", exchange, ExchangeSimulation::p99LatencyNanos)
                .description("Matching-engine submit latency, p99 (nanoseconds)")
                .register(registry);
    }
}
