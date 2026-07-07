package com.bonddesk.rates;

/**
 * A fixed-rate bullet bond: a {@code couponPct} annual coupon paid {@code frequency} times a year on
 * {@code face} notional, redeeming at {@code maturityYears}. Cash-flow times are measured from
 * settlement (assumed on a coupon date, so clean = dirty — accrued is handled separately at the
 * desk layer). All prices are per 100 face.
 */
public record Bond(double couponPct, double maturityYears, int frequency, double face) {

    public static Bond of(double couponPct, double maturityYears) {
        return new Bond(couponPct, maturityYears, 2, 100.0);   // US Treasuries: semi-annual
    }

    private int nCashflows() {
        return Math.max(1, (int) Math.round(maturityYears * frequency));
    }

    /** Cash-flow times in years (coupon dates up to and including maturity). */
    public double[] times() {
        int n = nCashflows();
        double[] t = new double[n];
        for (int k = 1; k <= n; k++) {
            t[k - 1] = (double) k / frequency;
        }
        return t;
    }

    /** Cash-flow amounts per 100 face (coupon each period; final adds redemption). */
    public double[] amounts() {
        int n = nCashflows();
        double coupon = couponPct / 100.0 / frequency * face;
        double[] a = new double[n];
        for (int k = 1; k <= n; k++) {
            a[k - 1] = coupon + (k == n ? face : 0.0);
        }
        return a;
    }
}
