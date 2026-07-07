package com.bonddesk.oms.strategy;

import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.MarketDataService;
import com.bonddesk.oms.strategy.StrategyDtos.CreateStrategyRequest;
import com.bonddesk.oms.strategy.StrategyDtos.ModifyStrategyRequest;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** Live-control behaviour added for the execution cockpit: pause/resume and in-place parameter modify. */
class StrategyControlTest {

    private StrategyService service() {
        MarketDataService md = mock(MarketDataService.class);
        when(md.book(anyString())).thenReturn(new LiveOrderBook("BTC-USD"));
        when(md.currentTradeSeq()).thenReturn(0L);
        Clock clock = Clock.fixed(Instant.parse("2024-01-01T00:00:00Z"), ZoneOffset.UTC);
        return new StrategyService(md, clock);
    }

    private CreateStrategyRequest pov() {
        return new CreateStrategyRequest("POV", "BTC-USD", "BUY", 1.0, 10, 0.1, null, null, null, null);
    }

    @Test
    void pauseRemovesFromActiveSetAndResumeRestores() {
        StrategyService svc = service();
        String id = svc.create(pov()).id();
        assertThat(svc.activeRuns()).hasSize(1);

        svc.pause(id);
        assertThat(svc.view(id).status()).isEqualTo("PAUSED");
        assertThat(svc.activeRuns()).isEmpty();          // the runner will skip it

        svc.resume(id);
        assertThat(svc.view(id).status()).isEqualTo("RUNNING");
        assertThat(svc.activeRuns()).hasSize(1);
    }

    @Test
    void modifyUpdatesPovParticipationInPlaceAndClamps() {
        StrategyService svc = service();
        StrategyRun run = svc.create(pov());
        assertThat(((PovExecution) run.strategy()).participation()).isEqualTo(0.1);

        svc.modify(run.id(), new ModifyStrategyRequest(0.5, null, null));
        assertThat(((PovExecution) run.strategy()).participation()).isEqualTo(0.5);

        svc.modify(run.id(), new ModifyStrategyRequest(5.0, null, null)); // above 1.0 → clamped
        assertThat(((PovExecution) run.strategy()).participation()).isEqualTo(1.0);
    }

    @Test
    void modifyUpdatesMakerGammaAndQuoteSize() {
        StrategyService svc = service();
        StrategyRun run = svc.create(new CreateStrategyRequest(
                "AVELLANEDA_STOIKOV", "BTC-USD", null, null, null, null, 1.5, 0.3, 60.0, 0.05));
        AvellanedaStoikovMaker mm = (AvellanedaStoikovMaker) run.strategy();
        assertThat(mm.gamma()).isEqualTo(0.3);
        assertThat(mm.quoteSize()).isEqualTo(0.05);

        svc.modify(run.id(), new ModifyStrategyRequest(null, 0.8, 0.2));
        assertThat(mm.gamma()).isEqualTo(0.8);
        assertThat(mm.quoteSize()).isEqualTo(0.2);
    }
}
