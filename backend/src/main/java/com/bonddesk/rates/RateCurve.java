package com.bonddesk.rates;

/**
 * A discount curve for one currency, held as continuously-compounded <b>zero rates</b> at a set of
 * pillar tenors, so a discount factor is simply {@code exp(-z(t)·t)}. Zero rates are linearly
 * interpolated between pillars and held flat beyond the ends. Built by bootstrapping a par curve
 * (see {@link CurveBootstrap}); the bump helpers below produce the shifted curves the risk engine
 * uses for parallel DV01, key-rate DV01, and curve shocks.
 *
 * <p>Immutable — every bump returns a new curve.
 */
public final class RateCurve {

    private final double[] tenors;   // pillar years, strictly ascending
    private final double[] zeros;    // continuously-compounded zero rates (decimal)

    public RateCurve(double[] tenors, double[] zeros) {
        if (tenors.length != zeros.length || tenors.length == 0) {
            throw new IllegalArgumentException("tenors/zeros length mismatch");
        }
        this.tenors = tenors;
        this.zeros = zeros;
    }

    public int pillarCount() {
        return tenors.length;
    }

    public double[] tenors() {
        return tenors.clone();
    }

    public double[] zeros() {
        return zeros.clone();
    }

    /** Continuously-compounded zero rate at {@code t} (linear interpolation, flat beyond the ends). */
    public double zero(double t) {
        int n = tenors.length;
        if (t <= tenors[0]) {
            return zeros[0];
        }
        if (t >= tenors[n - 1]) {
            return zeros[n - 1];
        }
        for (int i = 1; i < n; i++) {
            if (t <= tenors[i]) {
                double w = (t - tenors[i - 1]) / (tenors[i] - tenors[i - 1]);
                return zeros[i - 1] + w * (zeros[i] - zeros[i - 1]);
            }
        }
        return zeros[n - 1];
    }

    /** Discount factor to time {@code t}. */
    public double df(double t) {
        return Math.exp(-zero(t) * t);
    }

    /** Continuously-compounded forward rate between {@code t1} and {@code t2}. */
    public double forward(double t1, double t2) {
        return (zero(t2) * t2 - zero(t1) * t1) / (t2 - t1);
    }

    /** A parallel shift of the whole curve by {@code dz} (decimal, e.g. 0.0001 for +1bp). */
    public RateCurve parallelBump(double dz) {
        double[] z = zeros.clone();
        for (int i = 0; i < z.length; i++) {
            z[i] += dz;
        }
        return new RateCurve(tenors.clone(), z);
    }

    /**
     * Bump a single pillar's zero rate by {@code dz}. Because rates are linearly interpolated, this
     * produces the classic <b>triangular key-rate shock</b> — the bump is full at that pillar and
     * tapers linearly to zero at the neighbouring pillars — which is exactly what a key-rate DV01 needs.
     */
    public RateCurve bumpPillar(int pillar, double dz) {
        double[] z = zeros.clone();
        z[pillar] += dz;
        return new RateCurve(tenors.clone(), z);
    }
}
