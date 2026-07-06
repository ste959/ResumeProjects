package com.bonddesk.oms.fixedincome;

import java.time.LocalDate;

/**
 * A par-yield curve: yields (in percent) at a set of maturities (in years), sorted
 * ascending by tenor. Linear interpolation between tenors, flat extrapolation beyond the
 * ends — enough to discount a bond's cash flows off the real Treasury benchmark.
 */
public record YieldCurve(LocalDate asOf, double[] tenors, double[] yields, String source) {

    /** Interpolated par yield (percent) at {@code tenorYears}. */
    public double interpolate(double tenorYears) {
        int n = tenors.length;
        if (n == 0) {
            return 0.0;
        }
        if (tenorYears <= tenors[0]) {
            return yields[0];
        }
        if (tenorYears >= tenors[n - 1]) {
            return yields[n - 1];
        }
        for (int i = 1; i < n; i++) {
            if (tenorYears <= tenors[i]) {
                double w = (tenorYears - tenors[i - 1]) / (tenors[i] - tenors[i - 1]);
                return yields[i - 1] + w * (yields[i] - yields[i - 1]);
            }
        }
        return yields[n - 1];
    }
}
