package com.bonddesk.oms.strategy;

import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.LiveOrderBook.Level;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

class ExecutionStrategyTest {

    private static final Instant T = Instant.parse("2026-07-02T00:00:00Z");

    /** A book with effectively unlimited liquidity at price 100 on both sides. */
    private static LiveOrderBook deepBook() {
        LiveOrderBook book = new LiveOrderBook("BTC-USD");
        book.resetTo(List.of(new Level(new BigDecimal("100"), new BigDecimal("1000"))),
                List.of(new Level(new BigDecimal("100"), new BigDecimal("1000"))));
        return book;
    }

    private static void runToCompletion(ExecutionStrategy strat, StrategyRun run, double volume) {
        LiveOrderBook book = deepBook();
        MarketState state = new MarketState("BTC-USD", 100, 100, 100, 100, 0.0, volume);
        for (int i = 0; i < 100 && !strat.isDone(); i++) {
            strat.step(new StrategyContext(state, book, run, T));
        }
    }

    @Test
    void twapSplitsEvenlyAndCompletes() {
        TwapExecution twap = new TwapExecution(true, 10.0, 5);
        StrategyRun run = new StrategyRun("TWAP", "BTC-USD", twap, T);
        runToCompletion(twap, run, 0);

        assertThat(twap.isDone()).isTrue();
        assertThat(run.executedSize()).isCloseTo(10.0, within(1e-6));
        assertThat(run.book().fills()).hasSize(5);
        assertThat(run.book().fills()).allSatisfy(f -> assertThat(f.size()).isCloseTo(2.0, within(1e-6)));
    }

    @Test
    void almgrenChrissIsFrontLoaded() {
        AlmgrenChrissExecution ac = new AlmgrenChrissExecution(true, 12.0, 4, 0.6);
        StrategyRun run = new StrategyRun("AC", "BTC-USD", ac, T);
        runToCompletion(ac, run, 0);

        List<Fill> fills = run.book().fills();
        assertThat(run.executedSize()).isCloseTo(12.0, within(1e-6));
        // Risk-averse trader trades more early than late.
        assertThat(fills.get(0).size()).isGreaterThan(fills.get(fills.size() - 1).size());
    }

    @Test
    void povTracksVolume() {
        PovExecution pov = new PovExecution(true, 1.0, 20, 0.2);
        StrategyRun run = new StrategyRun("POV", "BTC-USD", pov, T);
        runToCompletion(pov, run, 1.0); // 0.2 * 1.0 = 0.2 per slice

        assertThat(run.executedSize()).isCloseTo(1.0, within(1e-6));
        assertThat(run.book().fills().get(0).size()).isCloseTo(0.2, within(1e-6));
    }
}
