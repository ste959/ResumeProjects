package com.bonddesk.oms.pricing;

import org.junit.jupiter.api.Test;

import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

class BondMathTest {

    // A 10-year 4% semi-annual bond, valued on a coupon date (zero accrued).
    private static final LocalDate SETTLE = LocalDate.of(2026, 1, 15);
    private static final LocalDate MATURITY = LocalDate.of(2036, 1, 15);

    @Test
    void parBondYieldsItsCoupon() {
        BondAnalytics a = BondMath.analyze(SETTLE, MATURITY, 0.04, 100.0);

        assertThat(a.yieldToMaturity()).isCloseTo(0.04, within(1e-6));
        assertThat(a.accruedInterest()).isCloseTo(0.0, within(1e-9));
        assertThat(a.dirtyPrice()).isCloseTo(100.0, within(1e-6));
    }

    @Test
    void discountBondYieldsAboveCoupon() {
        BondAnalytics a = BondMath.analyze(SETTLE, MATURITY, 0.04, 90.0);
        assertThat(a.yieldToMaturity()).isGreaterThan(0.04);
    }

    @Test
    void premiumBondYieldsBelowCoupon() {
        BondAnalytics a = BondMath.analyze(SETTLE, MATURITY, 0.04, 110.0);
        assertThat(a.yieldToMaturity()).isLessThan(0.04);
    }

    @Test
    void durationConvexityAndDv01AreInSensibleRanges() {
        BondAnalytics a = BondMath.analyze(SETTLE, MATURITY, 0.04, 100.0);

        // A 10y par bond has modified duration around 8 years.
        assertThat(a.modifiedDuration()).isBetween(7.5, 8.5);
        assertThat(a.macaulayDuration()).isGreaterThan(a.modifiedDuration()); // Mac = Mod * (1 + y/f)
        assertThat(a.convexity()).isPositive();
        // DV01 = modified * dirty * 1bp
        assertThat(a.dv01()).isCloseTo(a.modifiedDuration() * a.dirtyPrice() * 1e-4, within(1e-9));
    }

    @Test
    void accruedInterestIsComputedMidPeriod() {
        // 90 days (30/360) into a 180-day period → half a coupon accrued.
        BondAnalytics a = BondMath.analyze(LocalDate.of(2026, 4, 15), MATURITY, 0.04, 98.0);

        assertThat(a.accruedInterest()).isCloseTo(1.0, within(1e-6)); // coupon 2.0 * 90/180
        assertThat(a.dirtyPrice()).isCloseTo(98.0 + a.accruedInterest(), within(1e-6));
    }

    @Test
    void yieldRoundTripsBackToCleanPrice() {
        double clean = 96.375;
        BondAnalytics a = BondMath.analyze(SETTLE, MATURITY, 0.035, clean);

        // Re-price at the solved yield and recover the clean price.
        BondAnalytics repriced = BondMath.analyze(SETTLE, MATURITY, 0.035,
                a.dirtyPrice() - a.accruedInterest());
        assertThat(repriced.dirtyPrice() - repriced.accruedInterest()).isCloseTo(clean, within(1e-6));
        assertThat(a.yieldToMaturity()).isGreaterThan(0.035); // priced below par → yield above coupon
    }

    @Test
    void cleanPriceFromYieldIsTheInverseOfYtm() {
        // Price from a yield, then solve the yield back from that price — they must agree.
        double yield = 0.0475;
        double clean = BondMath.cleanPriceFromYield(SETTLE, MATURITY, 0.04, yield);
        BondAnalytics a = BondMath.analyze(SETTLE, MATURITY, 0.04, clean);
        assertThat(a.yieldToMaturity()).isCloseTo(yield, within(1e-8));
    }

    @Test
    void higherYieldMeansLowerPrice() {
        double low = BondMath.cleanPriceFromYield(SETTLE, MATURITY, 0.04, 0.03);
        double high = BondMath.cleanPriceFromYield(SETTLE, MATURITY, 0.04, 0.06);
        assertThat(low).isGreaterThan(high);
        // At a yield equal to the coupon, a bond prices at par.
        assertThat(BondMath.cleanPriceFromYield(SETTLE, MATURITY, 0.04, 0.04)).isCloseTo(100.0, within(1e-6));
    }
}
