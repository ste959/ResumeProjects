package com.bonddesk.oms.analytics;

import com.bonddesk.oms.AbstractPostgresIntegrationTest;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.TimeInForce;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.bonddesk.oms.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Exercises the raw-SQL analytics layer end to end against a real PostgreSQL. Uses
 * MICROSOFT (594918BR4, benchmark 68.40) — a security no other test trades — so the TCA
 * numbers are deterministic regardless of what else is in the shared test database.
 */
class AnalyticsServiceIntegrationTest extends AbstractPostgresIntegrationTest {

    private static final String MSFT = "594918BR4"; // AAA, benchmark clean price 68.40

    @Autowired
    private OrderService orders;

    @Autowired
    private AnalyticsService analytics;

    private void buyAndFill(String cusip, String qty, String price) {
        Order o = orders.create(new CreateOrderRequest(cusip, "PORT-ANALYTICS", "quant",
                OrderSide.BUY, OrderType.MARKET, TimeInForce.DAY, new BigDecimal(qty), null));
        orders.stage(o.getOrderRef());
        orders.route(o.getOrderRef());
        orders.recordFill(o.getOrderRef(), new BigDecimal(qty), new BigDecimal(price), "TW");
    }

    @Test
    void executionQualityComputesSlippageVsBenchmark() {
        buyAndFill(MSFT, "1000000", "69.0000"); // 0.60 over the 68.40 benchmark

        ExecutionQuality row = analytics.executionQuality().stream()
                .filter(r -> r.cusip().equals(MSFT) && r.side() == OrderSide.BUY)
                .findFirst().orElseThrow();

        assertThat(row.filledFace()).isEqualByComparingTo("1000000");
        assertThat(row.avgFillPrice()).isEqualByComparingTo("69.0000");
        assertThat(row.benchmarkPrice()).isEqualByComparingTo("68.4000");
        // (69.00 - 68.40) / 68.40 * 10_000 ≈ 87.7 bps, positive = paid over benchmark
        assertThat(row.slippageBps()).isEqualByComparingTo("87.7");
    }

    @Test
    void topSecuritiesRanksByFilledVolume() {
        buyAndFill(MSFT, "2000000", "69.0000");

        List<SecurityVolume> top = analytics.topSecuritiesByVolume(50);

        assertThat(top).isNotEmpty();
        assertThat(top).extracting(SecurityVolume::cusip).contains(MSFT);
        // Result is sorted by traded volume descending.
        for (int i = 1; i < top.size(); i++) {
            assertThat(top.get(i - 1).tradedFace()).isGreaterThanOrEqualTo(top.get(i).tradedFace());
        }
    }

    @Test
    void deskSummaryReportsFillRateInRange() {
        buyAndFill(MSFT, "1000000", "69.0000");

        DeskSummary s = analytics.deskSummary();

        assertThat(s.totalOrders()).isPositive();
        assertThat(s.filledOrders()).isPositive();
        assertThat(s.totalFilledFace()).isGreaterThanOrEqualTo(new BigDecimal("1000000"));
        assertThat(s.fillRatePct()).isBetween(BigDecimal.ZERO, new BigDecimal("100"));
    }

    @Test
    void dailyVolumeRunningTotalEqualsSumOfDays() {
        buyAndFill(MSFT, "1000000", "69.0000");

        List<DailyVolume> series = analytics.dailyVolume();

        assertThat(series).isNotEmpty();
        BigDecimal sumOfDays = series.stream()
                .map(DailyVolume::dailyFace)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal lastCumulative = series.get(series.size() - 1).cumulativeFace();
        assertThat(lastCumulative).isEqualByComparingTo(sumOfDays);
    }
}
