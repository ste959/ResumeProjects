package com.bonddesk.rates;

/**
 * Prices a bond off a discount curve and computes its full risk vector — the analytics a rates desk
 * actually trades on. (Distinct from {@code com.bonddesk.oms.pricing.BondMath}, which is single-bond,
 * yield-based DCF analytics; this one is curve-based z-spread/DV01/key-rate risk.)
 *
 * <ul>
 *   <li><b>Price / z-spread</b> — PV of cash flows off the curve plus a constant continuous spread;
 *       {@code zSpread} solves the spread that reprices to a market quote.</li>
 *   <li><b>DV01</b> — price change for a 1bp parallel curve shift.</li>
 *   <li><b>Key-rate DV01</b> — DV01 bucketed by curve pillar (bump one pillar, reprice), so you see
 *       <i>where</i> on the curve the risk sits, not just a single lumped number. The buckets sum to
 *       the parallel DV01.</li>
 *   <li><b>Spread DV01, convexity, modified &amp; Macaulay duration</b>.</li>
 * </ul>
 * All from first principles; nothing stored. Prices per 100 face.
 */
public final class BondMath {

    private static final double BP = 1e-4;

    private BondMath() {}

    /** Present value off the curve with a continuous z-spread (in bps). */
    public static double price(Bond b, RateCurve c, double zSpreadBps) {
        double sc = zSpreadBps * BP;
        double[] t = b.times(), a = b.amounts();
        double pv = 0;
        for (int i = 0; i < t.length; i++) {
            pv += a[i] * c.df(t[i]) * Math.exp(-sc * t[i]);
        }
        return pv;
    }

    /** The z-spread (bps) that reprices the bond to {@code marketClean} (bisection). */
    public static double zSpread(Bond b, RateCurve c, double marketClean) {
        double lo = -2000, hi = 5000;
        for (int it = 0; it < 200; it++) {
            double mid = 0.5 * (lo + hi);
            if (price(b, c, mid) > marketClean) lo = mid; else hi = mid;   // price falls as spread rises
        }
        return 0.5 * (lo + hi);
    }

    /** Yield-to-maturity (annualised, compounded at the coupon frequency) from a clean price. */
    public static double ytm(Bond b, double clean) {
        double[] t = b.times(), a = b.amounts();
        int f = b.frequency();
        double lo = -0.5, hi = 1.0;
        for (int it = 0; it < 200; it++) {
            double y = 0.5 * (lo + hi);
            if (pvAtYield(t, a, f, y) > clean) lo = y; else hi = y;
        }
        return 0.5 * (lo + hi);
    }

    private static double pvAtYield(double[] t, double[] a, int f, double y) {
        double pv = 0;
        for (int i = 0; i < t.length; i++) {
            pv += a[i] * Math.pow(1 + y / f, -f * t[i]);
        }
        return pv;
    }

    /** Price change for a 1bp parallel curve shift (per 100 face, positive). */
    public static double dv01(Bond b, RateCurve c, double zSpreadBps) {
        return price(b, c, zSpreadBps) - price(b, c.parallelBump(BP), zSpreadBps);
    }

    /** DV01 bucketed by curve pillar (bump each pillar 1bp). Buckets sum to the parallel DV01. */
    public static double[] keyRateDv01(Bond b, RateCurve c, double zSpreadBps) {
        double base = price(b, c, zSpreadBps);
        double[] kr = new double[c.pillarCount()];
        for (int j = 0; j < kr.length; j++) {
            kr[j] = base - price(b, c.bumpPillar(j, BP), zSpreadBps);
        }
        return kr;
    }

    /** Price change for a 1bp widening of the credit z-spread. */
    public static double spreadDv01(Bond b, RateCurve c, double zSpreadBps) {
        return price(b, c, zSpreadBps) - price(b, c, zSpreadBps + 1.0);
    }

    /** Second-order price sensitivity to a parallel yield move (per 100 face). */
    public static double convexity(Bond b, RateCurve c, double zSpreadBps) {
        double p = price(b, c, zSpreadBps);
        double up = price(b, c.parallelBump(BP), zSpreadBps);
        double dn = price(b, c.parallelBump(-BP), zSpreadBps);
        return (up + dn - 2 * p) / (p * BP * BP);
    }

    /** Modified duration in years (= DV01·10⁴ / price). */
    public static double modDuration(Bond b, RateCurve c, double zSpreadBps) {
        double p = price(b, c, zSpreadBps);
        return dv01(b, c, zSpreadBps) / p * 1e4;
    }

    /** Macaulay duration in years. */
    public static double macDuration(Bond b, RateCurve c, double zSpreadBps) {
        double y = ytm(b, price(b, c, zSpreadBps));
        return modDuration(b, c, zSpreadBps) * (1 + y / b.frequency());
    }
}
