package com.bonddesk.oms.observability;

import com.bonddesk.oms.exchange.ExchangeSimulation;
import com.bonddesk.oms.market.MarketDataService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** Unit tests for the custom Actuator health indicators — the UP/DOWN logic operators depend on. */
class HealthIndicatorTest {

    @Test
    void matchingEngine_up_whenBookIsTwoSided() {
        ExchangeSimulation sim = mock(ExchangeSimulation.class);
        when(sim.twoSided()).thenReturn(true);
        when(sim.acceptedOrders()).thenReturn(3058L);
        when(sim.trades()).thenReturn(1708L);
        when(sim.ordersPerSec()).thenReturn(84.0);

        Health h = new MatchingEngineHealthIndicator(sim).health();

        assertThat(h.getStatus()).isEqualTo(Status.UP);
        assertThat(h.getDetails()).containsEntry("acceptingOrders", true)
                .containsEntry("acceptedOrders", 3058L)
                .containsEntry("trades", 1708L);
    }

    @Test
    void matchingEngine_down_whenNotTwoSided() {
        ExchangeSimulation sim = mock(ExchangeSimulation.class);
        when(sim.twoSided()).thenReturn(false);

        Health h = new MatchingEngineHealthIndicator(sim).health();

        assertThat(h.getStatus()).isEqualTo(Status.DOWN);
        assertThat(h.getDetails()).containsEntry("acceptingOrders", false);
    }

    @Test
    void marketDataFeed_upIdle_whenNoDataYet() {
        MarketDataService md = mock(MarketDataService.class);
        when(md.lastUpdate()).thenReturn(null);   // feed disabled / never connected

        Health h = new MarketDataHealthIndicator(md).health();

        assertThat(h.getStatus()).isEqualTo(Status.UP);   // optional feed doesn't drag the app DOWN
        assertThat(h.getDetails()).containsKey("feed");
    }

    @Test
    void marketDataFeed_up_whenFresh() {
        MarketDataService md = mock(MarketDataService.class);
        when(md.lastUpdate()).thenReturn(Instant.now());

        assertThat(new MarketDataHealthIndicator(md).health().getStatus()).isEqualTo(Status.UP);
    }

    @Test
    void marketDataFeed_down_whenStale() {
        MarketDataService md = mock(MarketDataService.class);
        when(md.lastUpdate()).thenReturn(Instant.now().minus(5, ChronoUnit.MINUTES));

        Health h = new MarketDataHealthIndicator(md).health();

        assertThat(h.getStatus()).isEqualTo(Status.DOWN);
        assertThat(h.getDetails()).containsKey("secondsSinceUpdate");
    }
}
