package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.bonddesk.oms.equities.AlpacaBrokerClient;
import com.bonddesk.oms.repository.SecurityRepository;
import com.bonddesk.oms.risk.RiskLimitProperties;
import com.bonddesk.oms.service.OrderService;
import com.bonddesk.oms.service.PositionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Unit tests for the rebalance sizing/routing logic with all collaborators mocked, so the
 * arithmetic (target shares, deltas, side/short classification, projected gross, risk gating)
 * and the routing side effects are verified without a database or a live venue.
 */
class RebalanceServiceTest {

    private static final String PORTFOLIO = "EQUITY-PAPER";
    private static final BigDecimal CAPITAL = new BigDecimal("100000");

    private TargetBookLoader loader;
    private PositionService positions;
    private OrderService orders;
    private SecurityRepository securities;
    private AlpacaBrokerClient broker;
    private RiskLimitProperties riskLimits;
    private RebalanceProperties rebalanceProps;
    private RebalanceService service;

    @BeforeEach
    void setUp() {
        loader = mock(TargetBookLoader.class);
        positions = mock(PositionService.class);
        orders = mock(OrderService.class);
        securities = mock(SecurityRepository.class);
        broker = mock(AlpacaBrokerClient.class);
        riskLimits = mock(RiskLimitProperties.class);
        rebalanceProps = mock(RebalanceProperties.class);
        service = new RebalanceService(loader, positions, orders, securities, broker, riskLimits,
                rebalanceProps);

        // Generous default caps unless a test overrides them (the rebalance uses the tighter one).
        when(riskLimits.getMaxGrossNotional()).thenReturn(new BigDecimal("100000000"));
        when(rebalanceProps.getMaxGrossNotional()).thenReturn(new BigDecimal("100000000"));
        when(positions.forPortfolio(anyString())).thenReturn(List.of());
    }

    // ---------- helpers ----------

    private static TargetWeight tw(String symbol, String weight, String price) {
        return new TargetWeight(symbol, new BigDecimal(weight), new BigDecimal(price));
    }

    private void bookOf(TargetWeight... names) {
        TargetBook book = new TargetBook("2026-07-02", "neutralized_momentum",
                new BigDecimal("0.5"), new BigDecimal("-0.5"), List.of(names));
        when(loader.load()).thenReturn(book);
    }

    private Position positionOf(String ticker, String netQty) {
        Security s = mock(Security.class);
        when(s.getTicker()).thenReturn(ticker);
        Position p = mock(Position.class);
        when(p.getSecurity()).thenReturn(s);
        when(p.getNetQuantity()).thenReturn(new BigDecimal(netQty));
        return p;
    }

    private PlannedTrade tradeFor(RebalancePlan plan, String symbol) {
        return plan.trades().stream().filter(t -> t.symbol().equals(symbol)).findFirst().orElseThrow();
    }

    // ---------- (a) sizing ----------

    @Test
    void sizesWholeSharesFromWeightTimesCapitalOverPrice() {
        bookOf(tw("AAA", "0.05", "100"));   // 0.05 * 100000 / 100 = 50 shares

        RebalancePlan plan = service.plan(CAPITAL, PORTFOLIO);

        PlannedTrade t = tradeFor(plan, "AAA");
        assertThat(t.targetShares()).isEqualByComparingTo("50");
        assertThat(t.qty()).isEqualByComparingTo("50");
        assertThat(t.side()).isEqualTo(OrderSide.BUY);
    }

    @Test
    void roundsHalfUpToWholeShares() {
        bookOf(tw("BBB", "0.0005", "20"));  // 0.0005 * 100000 / 20 = 2.5 -> 3

        RebalancePlan plan = service.plan(CAPITAL, PORTFOLIO);

        assertThat(tradeFor(plan, "BBB").targetShares()).isEqualByComparingTo("3");
    }

    // ---------- (b) delta vs existing position + sub-1 skip ----------

    @Test
    void deltaIsTargetMinusCurrentPosition() {
        bookOf(tw("CCC", "0.05", "100"));   // target 50
        List<Position> held = List.of(positionOf("CCC", "48"));
        when(positions.forPortfolio(PORTFOLIO)).thenReturn(held);

        RebalancePlan plan = service.plan(CAPITAL, PORTFOLIO);

        PlannedTrade t = tradeFor(plan, "CCC");
        assertThat(t.currentShares()).isEqualByComparingTo("48");
        assertThat(t.qty()).isEqualByComparingTo("2");    // 50 - 48
        assertThat(t.side()).isEqualTo(OrderSide.BUY);
        assertThat(t.shortSale()).isFalse();
    }

    @Test
    void skipsSubOneShareDelta() {
        bookOf(tw("DDD", "0.05", "100"));   // target 50
        List<Position> held = List.of(positionOf("DDD", "49.5"));
        when(positions.forPortfolio(PORTFOLIO)).thenReturn(held);

        RebalancePlan plan = service.plan(CAPITAL, PORTFOLIO);

        assertThat(plan.trades()).isEmpty();
    }

    // ---------- (c) side / short classification ----------

    @Test
    void negativeWeightNoPositionIsSellAndShort() {
        bookOf(tw("EEE", "-0.05", "100"));  // target -50, no position

        RebalancePlan plan = service.plan(CAPITAL, PORTFOLIO);

        PlannedTrade t = tradeFor(plan, "EEE");
        assertThat(t.targetShares()).isEqualByComparingTo("-50");
        assertThat(t.side()).isEqualTo(OrderSide.SELL);
        assertThat(t.qty()).isEqualByComparingTo("50");
        assertThat(t.shortSale()).isTrue();
    }

    // ---------- (d) projected gross + risk gating ----------

    @Test
    void computesProjectedGrossNotionalAcrossAllNames() {
        bookOf(tw("FFF", "0.05", "100"), tw("GGG", "-0.05", "100")); // 5000 + 5000

        RebalancePlan plan = service.plan(CAPITAL, PORTFOLIO);

        assertThat(plan.projectedGrossNotional()).isEqualByComparingTo("10000");
        assertThat(plan.withinRiskLimit()).isTrue();
    }

    @Test
    void blocksAndRoutesNothingWhenProjectedGrossExceedsLimit() {
        bookOf(tw("FFF", "0.05", "100"), tw("GGG", "-0.05", "100")); // projected gross 10000
        when(riskLimits.getMaxGrossNotional()).thenReturn(new BigDecimal("9000"));

        RebalanceResult result = service.execute(CAPITAL, PORTFOLIO, false);

        assertThat(result.status()).isEqualTo("BLOCKED_RISK_LIMIT");
        assertThat(result.withinRiskLimit()).isFalse();
        assertThat(result.outcomes()).isEmpty();
        verifyNoInteractions(orders);
    }

    // ---------- (e) dry run ----------

    @Test
    void dryRunReturnsPlanWithoutRouting() {
        bookOf(tw("HHH", "0.05", "100"));

        RebalanceResult result = service.execute(CAPITAL, PORTFOLIO, true);

        assertThat(result.status()).isEqualTo("DRY_RUN");
        assertThat(result.plannedTradeCount()).isEqualTo(1);
        assertThat(result.outcomes()).isEmpty();
        verifyNoInteractions(orders);
        verify(securities, never()).save(any());
    }

    // ---------- (f) live routing ----------

    @Test
    void liveExecuteRoutesEachDeltaAndSkipsNonShortableShort() {
        bookOf(
                tw("LONGA", "0.05", "100"),    // BUY 50 (not short)
                tw("SHORTNO", "-0.05", "100"), // short, not shortable -> skipped
                tw("SHORTOK", "-0.05", "100")  // short, shortable -> SELL 50
        );
        when(broker.brokerReachable()).thenReturn(true);
        when(broker.isShortable("SHORTNO")).thenReturn(false);
        when(broker.isShortable("SHORTOK")).thenReturn(true);

        Order created = mock(Order.class);
        when(created.getOrderRef()).thenReturn("ref-1");
        when(orders.create(any(CreateOrderRequest.class))).thenReturn(created);

        RebalanceResult result = service.execute(CAPITAL, PORTFOLIO, false);

        assertThat(result.status()).isEqualTo("ROUTED");
        assertThat(result.routed()).isEqualTo(2);   // LONGA + SHORTOK
        assertThat(result.skipped()).isEqualTo(1);  // SHORTNO
        assertThat(result.rejected()).isZero();

        // Two names routed: create + stage + route each.
        verify(orders, times(2)).create(any(CreateOrderRequest.class));
        verify(orders, times(2)).stage("ref-1");
        verify(orders, times(2)).route("ref-1");

        TradeOutcome skipped = result.outcomes().stream()
                .filter(o -> o.symbol().equals("SHORTNO")).findFirst().orElseThrow();
        assertThat(skipped.status()).isEqualTo(TradeOutcome.Status.SKIPPED);
        assertThat(skipped.detail()).isEqualTo("not shortable");
    }

    @Test
    void liveExecuteRecordsRejectionWhenOrderCreateThrows() {
        bookOf(tw("ZZZ", "0.05", "100"));
        when(broker.brokerReachable()).thenReturn(true);
        when(orders.create(any(CreateOrderRequest.class)))
                .thenThrow(new IllegalStateException("compliance blocked"));

        RebalanceResult result = service.execute(CAPITAL, PORTFOLIO, false);

        assertThat(result.status()).isEqualTo("ROUTED");
        assertThat(result.rejected()).isEqualTo(1);
        assertThat(result.outcomes().get(0).status()).isEqualTo(TradeOutcome.Status.REJECTED);
        assertThat(result.outcomes().get(0).detail()).contains("compliance blocked");
    }
}
