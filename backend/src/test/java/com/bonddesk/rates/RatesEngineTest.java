package com.bonddesk.rates;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** Correctness of the rates engine — the invariants a rates desk relies on. */
class RatesEngineTest {

    private static final double[] TENORS = {0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30};
    private static final double[] PAR = {4.35, 4.20, 4.00, 3.80, 3.75, 3.85, 4.00, 4.20, 4.55, 4.50};

    private RateCurve flat(double z) {
        double[] zeros = new double[TENORS.length];
        java.util.Arrays.fill(zeros, z);
        return new RateCurve(TENORS.clone(), zeros);
    }

    @Test
    void bootstrappedCurveRepricesEveryParInstrumentToPar() {
        RateCurve c = CurveBootstrap.fromPar(TENORS, PAR);
        double annuity = 0;
        for (int n = 0; n < TENORS.length; n++) {
            double tau = TENORS[n] - (n == 0 ? 0 : TENORS[n - 1]);
            double df = c.df(TENORS[n]);
            annuity += tau * df;
            double parLeg = (PAR[n] / 100.0) * annuity + df;   // par swap PV should be 1
            assertThat(parLeg).isCloseTo(1.0, org.assertj.core.data.Offset.offset(1e-6));
        }
    }

    @Test
    void zeroCouponDv01MatchesClosedForm() {
        RateCurve c = flat(0.04);
        Bond zcb = new Bond(0.0, 5.0, 2, 100.0);           // pays only 100 at t=5
        double price = BondMath.price(zcb, c, 0);
        assertThat(price).isCloseTo(100 * Math.exp(-0.04 * 5), org.assertj.core.data.Offset.offset(1e-6));
        // dP/dz = −T·P  ⇒  DV01 ≈ P·T·1e-4
        assertThat(BondMath.dv01(zcb, c, 0)).isCloseTo(price * 5 * 1e-4, withinPct(price * 5 * 1e-4, 0.01));
    }

    @Test
    void keyRateDv01LocalisesToTheMaturityPillar() {
        RateCurve c = CurveBootstrap.fromPar(TENORS, PAR);
        Bond zcb = new Bond(0.0, 5.0, 2, 100.0);           // all risk at t=5, which is a pillar
        double[] kr = BondMath.keyRateDv01(zcb, c, 0);
        double dv01 = BondMath.dv01(zcb, c, 0);
        int fiveYr = 5;                                    // TENORS[5] == 5
        assertThat(kr[fiveYr]).isCloseTo(dv01, withinPct(dv01, 0.01));
        for (int j = 0; j < kr.length; j++) {
            if (j != fiveYr) assertThat(Math.abs(kr[j])).isLessThan(1e-8);
        }
    }

    @Test
    void keyRateDv01BucketsSumToParallelDv01() {
        RateCurve c = CurveBootstrap.fromPar(TENORS, PAR);
        Bond bond = new Bond(4.0, 10.0, 2, 100.0);
        double dv01 = BondMath.dv01(bond, c, 25);
        double sum = 0;
        for (double kr : BondMath.keyRateDv01(bond, c, 25)) sum += kr;
        assertThat(sum).isCloseTo(dv01, withinPct(dv01, 0.01));
    }

    @Test
    void dv01AndDurationRiseWithMaturity() {
        RateCurve c = CurveBootstrap.fromPar(TENORS, PAR);
        Bond twoYr = new Bond(4.0, 2.0, 2, 100.0);
        Bond tenYr = new Bond(4.0, 10.0, 2, 100.0);
        assertThat(BondMath.dv01(tenYr, c, 0)).isGreaterThan(BondMath.dv01(twoYr, c, 0));
        assertThat(BondMath.modDuration(tenYr, c, 0)).isGreaterThan(BondMath.modDuration(twoYr, c, 0));
        assertThat(BondMath.modDuration(tenYr, c, 0)).isBetween(7.0, 9.0);   // a ~10y bond
    }

    @Test
    void zSpreadRepricesToTheQuote() {
        RateCurve c = CurveBootstrap.fromPar(TENORS, PAR);
        Bond bond = new Bond(4.0, 7.0, 2, 100.0);
        double quote = BondMath.price(bond, c, 0) - 2.0;   // 2 points cheap → a positive z-spread
        double s = BondMath.zSpread(bond, c, quote);
        assertThat(s).isGreaterThan(0);
        assertThat(BondMath.price(bond, c, s)).isCloseTo(quote, org.assertj.core.data.Offset.offset(1e-4));
    }

    private static org.assertj.core.data.Percentage withinPct(double base, double frac) {
        return org.assertj.core.data.Percentage.withPercentage(Math.max(0.5, frac * 100));
    }
}
