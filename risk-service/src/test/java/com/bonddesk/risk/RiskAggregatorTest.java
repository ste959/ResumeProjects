package com.bonddesk.risk;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

class RiskAggregatorTest {

    private OrderEvent event(String ref, String portfolio, String status, String filled) {
        return new OrderEvent("ORDER_" + status, ref, "912828YK0", portfolio, status,
                new BigDecimal("1000000"), new BigDecimal(filled), Instant.parse("2026-07-02T12:00:00Z"));
    }

    @Test
    void aggregatesLatestStatePerOrder() {
        RiskAggregator agg = new RiskAggregator();
        agg.record(event("A", "PORT-1", "ROUTED", "0"));
        agg.record(event("A", "PORT-1", "PARTIALLY_FILLED", "600000"));
        agg.record(event("A", "PORT-1", "FILLED", "1000000")); // supersedes earlier A events
        agg.record(event("B", "PORT-1", "REJECTED", "0"));
        agg.record(event("C", "PORT-2", "ROUTED", "0"));

        DeskRiskSummary s = agg.summary();

        assertThat(s.totalOrders()).isEqualTo(3);                 // A, B, C — not 5 events
        assertThat(s.totalFilledFace()).isEqualByComparingTo("1000000");
        assertThat(s.ordersByStatus()).containsEntry("FILLED", 1L)
                .containsEntry("REJECTED", 1L).containsEntry("ROUTED", 1L);
        assertThat(s.portfolios()).hasSize(2);
    }

    @Test
    void replayingEventsIsIdempotent() {
        RiskAggregator agg = new RiskAggregator();
        for (int i = 0; i < 3; i++) {
            agg.record(event("A", "PORT-1", "FILLED", "1000000"));
        }
        assertThat(agg.summary().totalOrders()).isEqualTo(1);
        assertThat(agg.summary().totalFilledFace()).isEqualByComparingTo("1000000");
    }

    @Test
    void tracksWorkingAndRejectedPerPortfolio() {
        RiskAggregator agg = new RiskAggregator();
        agg.record(event("A", "PORT-1", "ROUTED", "0"));
        agg.record(event("B", "PORT-1", "REJECTED", "0"));
        agg.record(event("C", "PORT-1", "FILLED", "1000000"));

        PortfolioRisk p1 = agg.summary().portfolios().get(0);
        assertThat(p1.portfolio()).isEqualTo("PORT-1");
        assertThat(p1.orderCount()).isEqualTo(3);
        assertThat(p1.workingOrders()).isEqualTo(1);   // ROUTED
        assertThat(p1.rejectedOrders()).isEqualTo(1);
    }
}
