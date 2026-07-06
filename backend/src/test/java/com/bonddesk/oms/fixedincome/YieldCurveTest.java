package com.bonddesk.oms.fixedincome;

import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

/** Linear interpolation between tenors, flat extrapolation past the ends. */
class YieldCurveTest {

    private final YieldCurve curve = new YieldCurve(
            LocalDate.of(2026, 7, 6),
            new double[]{1, 2, 5, 10},
            new double[]{4.0, 3.8, 3.9, 4.2},
            "test");

    @Test
    void returnsExactYieldAtAKnownTenor() {
        assertThat(curve.interpolate(2)).isCloseTo(3.8, within(1e-9));
        assertThat(curve.interpolate(10)).isCloseTo(4.2, within(1e-9));
    }

    @Test
    void interpolatesLinearlyBetweenTenors() {
        assertThat(curve.interpolate(1.5)).isCloseTo(3.9, within(1e-9));   // midpoint of 4.0 and 3.8
        assertThat(curve.interpolate(7.5)).isCloseTo(4.05, within(1e-9));  // 3.9 + 0.5*(4.2-3.9)
    }

    @Test
    void clampsBeyondTheEnds() {
        assertThat(curve.interpolate(0.25)).isCloseTo(4.0, within(1e-9));  // below shortest tenor
        assertThat(curve.interpolate(30)).isCloseTo(4.2, within(1e-9));    // above longest tenor
    }
}
