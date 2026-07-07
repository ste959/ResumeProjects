package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.equities.AlpacaBrokerClient;
import com.bonddesk.oms.equities.AlpacaBrokerClient.MarketClock;
import com.bonddesk.oms.equities.AlpacaMarketDataClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for the market-hours auto-rebalancer's guard logic with a fixed clock and mocked
 * collaborators: it must do nothing when disabled, nothing when the market is closed, nothing when
 * it already ran today, and exactly one reconcile-then-execute (recording state) on an open new day.
 */
class RebalanceSchedulerTest {

    // 2026-07-07 15:00 UTC → 11:00 America/New_York, so the exchange-zone date is 2026-07-07.
    private static final Instant NOW = Instant.parse("2026-07-07T15:00:00Z");
    private static final LocalDate TODAY = LocalDate.ofInstant(NOW, ZoneId.of("America/New_York"));
    private static final String PORTFOLIO = "EQUITY-PAPER";
    private static final BigDecimal CAPITAL = new BigDecimal("100000");

    private RebalanceProperties props;
    private AlpacaBrokerClient broker;
    private AlpacaMarketDataClient marketData;
    private TargetBookLoader loader;
    private RebalanceService rebalanceService;
    private PositionReconciler reconciler;
    private RebalanceState state;
    private RebalanceScheduler scheduler;

    @BeforeEach
    void setUp() {
        props = mock(RebalanceProperties.class);
        broker = mock(AlpacaBrokerClient.class);
        marketData = mock(AlpacaMarketDataClient.class);
        loader = mock(TargetBookLoader.class);
        rebalanceService = mock(RebalanceService.class);
        reconciler = mock(PositionReconciler.class);
        state = mock(RebalanceState.class);
        Clock clock = Clock.fixed(NOW, ZoneId.of("UTC"));
        scheduler = new RebalanceScheduler(props, broker, marketData, loader, rebalanceService,
                reconciler, state, clock);

        when(props.getGrossCapital()).thenReturn(CAPITAL);
        when(props.getPortfolio()).thenReturn(PORTFOLIO);
    }

    private MarketClock open() {
        return new MarketClock(true, NOW.toString(), null, null);
    }

    @Test
    void doesNothingWhenAutoDisabled() {
        when(props.isAutoEnabled()).thenReturn(false);

        scheduler.tick();

        verify(broker, never()).clock();
        verify(reconciler, never()).reconcile();
        verify(rebalanceService, never()).execute(any(), anyString(), anyBoolean(), any());
    }

    @Test
    void doesNothingWhenMarketClosed() {
        when(props.isAutoEnabled()).thenReturn(true);
        when(broker.clock()).thenReturn(new MarketClock(false, NOW.toString(), null, null));

        scheduler.tick();

        verify(reconciler, never()).reconcile();
        verify(rebalanceService, never()).execute(any(), anyString(), anyBoolean(), any());
    }

    @Test
    void doesNothingWhenAlreadyRanToday() {
        when(props.isAutoEnabled()).thenReturn(true);
        when(broker.clock()).thenReturn(open());
        when(state.lastRunDate()).thenReturn(TODAY);

        scheduler.tick();

        verify(reconciler, never()).reconcile();
        verify(rebalanceService, never()).execute(any(), anyString(), anyBoolean(), any());
    }

    @Test
    void reconcilesThenExecutesOnceAndRecordsOnOpenNewDay() {
        when(props.isAutoEnabled()).thenReturn(true);
        when(broker.clock()).thenReturn(open());
        when(state.lastRunDate()).thenReturn(null); // never ran

        TargetBook book = new TargetBook("2026-07-06", "neutralized_momentum",
                new BigDecimal("0.5"), new BigDecimal("-0.5"),
                List.of(new TargetWeight("AAPL", new BigDecimal("0.05"), new BigDecimal("190"))));
        when(loader.load()).thenReturn(book);

        Map<String, BigDecimal> marks = Map.of("AAPL", new BigDecimal("191.00"));
        when(marketData.latestPrices(any())).thenReturn(marks);

        RebalanceResult result = mock(RebalanceResult.class);
        when(result.status()).thenReturn("ROUTED");
        when(rebalanceService.execute(eq(CAPITAL), eq(PORTFOLIO), eq(false), eq(marks)))
                .thenReturn(result);

        scheduler.tick();

        InOrder order = inOrder(reconciler, rebalanceService, state);
        order.verify(reconciler).reconcile();
        order.verify(rebalanceService).execute(eq(CAPITAL), eq(PORTFOLIO), eq(false), eq(marks));
        order.verify(state).record(eq(NOW), eq(TODAY), eq(result));
    }
}
