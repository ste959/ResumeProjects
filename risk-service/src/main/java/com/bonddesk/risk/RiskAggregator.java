package com.bonddesk.risk;

import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * Maintains a live, in-memory view of desk risk from the order-event stream.
 *
 * <p>Events are lifecycle updates keyed by order reference, so rather than summing every
 * event (which would double-count), we keep the last-arrived event per order and derive all
 * aggregates from that current-state map. It is <em>last-arrived-wins</em>, which is safe because
 * all events for one order share a partition and are therefore totally ordered — so the last one to
 * arrive is the newest. That makes the aggregation idempotent under redelivery: replaying the topic
 * (in that per-key order) yields the same numbers.
 */
@Component
public class RiskAggregator {

    private static final Set<String> WORKING = Set.of("NEW", "STAGED", "ROUTED", "PARTIALLY_FILLED");

    private final Map<String, OrderEvent> latestByRef = new ConcurrentHashMap<>();

    public void record(OrderEvent event) {
        if (event.orderRef() != null) {
            latestByRef.put(event.orderRef(), event);
        }
    }

    public DeskRiskSummary summary() {
        List<OrderEvent> current = List.copyOf(latestByRef.values());

        // groupingBy throws NPE on a null classifier key, so coalesce missing status/portfolio to a
        // sentinel: one partial event (e.g. a field dropped by ignore-unknown deserialization) must
        // not take down the whole /risk/summary endpoint.
        Map<String, Long> byStatus = current.stream()
                .collect(Collectors.groupingBy(e -> nzStr(e.status()), Collectors.counting()));

        BigDecimal totalFilled = current.stream()
                .map(e -> nz(e.filledQuantity()))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        List<PortfolioRisk> portfolios = current.stream()
                .collect(Collectors.groupingBy(e -> nzStr(e.portfolio())))
                .entrySet().stream()
                .map(RiskAggregator::toPortfolioRisk)
                .sorted(Comparator.comparing(PortfolioRisk::portfolio))
                .toList();

        return new DeskRiskSummary(current.size(), totalFilled, byStatus, portfolios);
    }

    private static PortfolioRisk toPortfolioRisk(Map.Entry<String, List<OrderEvent>> entry) {
        List<OrderEvent> events = entry.getValue();
        long working = events.stream().filter(e -> WORKING.contains(e.status())).count();
        long rejected = events.stream().filter(e -> "REJECTED".equals(e.status())).count();
        BigDecimal filled = events.stream().map(e -> nz(e.filledQuantity()))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return new PortfolioRisk(entry.getKey(), events.size(), working, rejected, filled);
    }

    private static BigDecimal nz(BigDecimal v) {
        return v == null ? BigDecimal.ZERO : v;
    }

    private static String nzStr(String v) {
        return v == null ? "UNKNOWN" : v;
    }
}
