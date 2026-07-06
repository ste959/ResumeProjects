package com.bonddesk.oms.backtest;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

class ScenarioTransformTest {

    private static final Instant T0 = Instant.parse("2026-01-01T00:00:00Z");

    private static L2Event event(String kind, String side, String price, String size, Instant t) {
        return new L2Event(1, t, "BTC-USD", kind, side, new BigDecimal(price), new BigDecimal(size));
    }

    @Test
    void identityWhenNothingIsScaled() {
        ScenarioTransform t = new ScenarioTransform(1, 1, 1, 0, 0, 0);
        t.start(T0);
        L2Event out = t.apply(event("UPD", "B", "100", "5", T0));
        assertThat(out.price()).isEqualByComparingTo("100");
        assertThat(out.size()).isEqualByComparingTo("5");
    }

    @Test
    void liquidityScaleScalesSizeNotPrice() {
        ScenarioTransform t = new ScenarioTransform(1, 1, 2.0, 0, 0, 0);
        t.start(T0);
        L2Event out = t.apply(event("UPD", "B", "100", "5", T0));
        assertThat(out.size()).isEqualByComparingTo("10"); // thicker book
        assertThat(out.price()).isEqualByComparingTo("100");
    }

    @Test
    void driftTrendsThePriceOverTime() {
        // 100 bps/min → +1% after one minute.
        ScenarioTransform t = new ScenarioTransform(1, 1, 1, 100, 0, 0);
        t.start(T0);
        L2Event out = t.apply(event("UPD", "A", "100", "5", T0.plusSeconds(60)));
        assertThat(out.price().doubleValue()).isCloseTo(101.0, within(1e-6));
    }

    @Test
    void spreadScaleWidensAroundTheMid() {
        // Seed the mid at 100 with a trade, then widen an ask sitting above it.
        ScenarioTransform t = new ScenarioTransform(1, 2.0, 1, 0, 0, 0);
        t.start(T0);
        t.apply(event("TRD", "B", "100", "1", T0)); // seeds refMid = 100
        L2Event ask = t.apply(event("UPD", "A", "101", "5", T0));
        // The ask sat 1 above the mid; at 2x spread it should sit ~2 above.
        assertThat(ask.price().doubleValue()).isGreaterThan(101.0);
    }
}
