package com.bonddesk.oms.pricing;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Fixed-income analytics from discounted cash flows: yield to maturity (solved with
 * Newton–Raphson), accrued interest, duration, convexity and DV01. Semi-annual coupons,
 * 30/360 day count, priced per 100 of par.
 *
 * <p>The maths, not a library, is the point here — this is deliberately hand-rolled to
 * show the numerical method (an iterative root-find plus analytic derivatives).
 */
public final class BondMath {

    private static final int FREQ = 2;              // semi-annual
    private static final double FACE = 100.0;       // price per 100 par
    private static final int DAYS_IN_PERIOD = 180;  // 30/360
    private static final int MAX_ITERATIONS = 100;
    private static final double TOLERANCE = 1e-10;

    private BondMath() {
    }

    /**
     * @param settlement  valuation date
     * @param maturity    final coupon / principal date
     * @param couponRate  annual coupon as a decimal (0.04 = 4%)
     * @param cleanPrice  quoted clean price per 100 par
     */
    public static BondAnalytics analyze(LocalDate settlement, LocalDate maturity,
                                        double couponRate, double cleanPrice) {
        if (!maturity.isAfter(settlement)) {
            throw new IllegalArgumentException("maturity must be after settlement");
        }
        List<LocalDate> schedule = futureCouponDates(settlement, maturity);
        LocalDate lastCoupon = schedule.get(0).minusMonths(12 / FREQ);

        double couponPmt = couponRate / FREQ * FACE;
        int accruedDays = days30360(lastCoupon, settlement);
        double w = 1.0 - (double) accruedDays / DAYS_IN_PERIOD;   // fraction of current period remaining
        double accrued = couponPmt * accruedDays / DAYS_IN_PERIOD;
        double targetDirty = cleanPrice + accrued;

        double[] times = new double[schedule.size()];   // time to each coupon, in periods
        double[] cashflows = new double[schedule.size()];
        for (int k = 0; k < schedule.size(); k++) {
            times[k] = w + k;
            cashflows[k] = couponPmt + (k == schedule.size() - 1 ? FACE : 0.0);
        }

        double y = solveYtm(times, cashflows, targetDirty, couponRate);
        double per = y / FREQ;

        double dirty = 0, weightedTime = 0, convexNum = 0;
        for (int k = 0; k < times.length; k++) {
            double df = Math.pow(1 + per, -times[k]);
            double pv = cashflows[k] * df;
            dirty += pv;
            weightedTime += (times[k] / FREQ) * pv;                       // years
            convexNum += pv * times[k] * (times[k] + 1);
        }

        double macaulay = weightedTime / dirty;
        double modified = macaulay / (1 + per);
        double convexity = convexNum / (dirty * Math.pow(1 + per, 2) * FREQ * FREQ);
        double dv01 = modified * dirty * 1e-4;

        return new BondAnalytics(y, accrued, dirty, macaulay, modified, convexity, dv01);
    }

    /**
     * The inverse of {@link #analyze}: the clean price per 100 par that a given yield
     * implies. Used by the RFQ dealer-quote engine, which prices bonds from a yield
     * (curve + credit spread) rather than solving a yield from a price.
     *
     * @param yield annual yield to maturity as a decimal (0.045 = 4.5%)
     */
    public static double cleanPriceFromYield(LocalDate settlement, LocalDate maturity,
                                             double couponRate, double yield) {
        if (!maturity.isAfter(settlement)) {
            throw new IllegalArgumentException("maturity must be after settlement");
        }
        List<LocalDate> schedule = futureCouponDates(settlement, maturity);
        LocalDate lastCoupon = schedule.get(0).minusMonths(12 / FREQ);

        double couponPmt = couponRate / FREQ * FACE;
        int accruedDays = days30360(lastCoupon, settlement);
        double w = 1.0 - (double) accruedDays / DAYS_IN_PERIOD;
        double accrued = couponPmt * accruedDays / DAYS_IN_PERIOD;

        double per = yield / FREQ;
        double dirty = 0;
        for (int k = 0; k < schedule.size(); k++) {
            double t = w + k;
            double cf = couponPmt + (k == schedule.size() - 1 ? FACE : 0.0);
            dirty += cf * Math.pow(1 + per, -t);
        }
        return dirty - accrued;
    }

    /** Newton–Raphson on dirtyPrice(y) − target, with an analytic derivative. */
    private static double solveYtm(double[] times, double[] cashflows, double target, double guess) {
        double y = guess > 0 ? guess : 0.05;
        for (int iter = 0; iter < MAX_ITERATIONS; iter++) {
            double per = y / FREQ;
            double price = 0, dPrice = 0;
            for (int k = 0; k < times.length; k++) {
                double base = 1 + per;
                double df = Math.pow(base, -times[k]);
                price += cashflows[k] * df;
                // d/dy of CF*(1+y/f)^(-t) = CF * (-t/f) * (1+y/f)^(-t-1)
                dPrice += cashflows[k] * (-times[k] / FREQ) * Math.pow(base, -times[k] - 1);
            }
            double diff = price - target;
            if (Math.abs(diff) < TOLERANCE) {
                return y;
            }
            double step = diff / dPrice;
            y -= step;
            if (y <= -0.99) {  // keep the discount factor well-defined
                y = -0.5;
            }
        }
        return y;
    }

    /** Coupon dates strictly after settlement, ascending, ending at maturity. */
    private static List<LocalDate> futureCouponDates(LocalDate settlement, LocalDate maturity) {
        List<LocalDate> dates = new ArrayList<>();
        LocalDate d = maturity;
        while (d.isAfter(settlement)) {
            dates.add(d);
            d = d.minusMonths(12 / FREQ);
        }
        Collections.reverse(dates);
        return dates;
    }

    /** 30/360 (US NASD) day count between two dates. */
    static int days30360(LocalDate start, LocalDate end) {
        int d1 = start.getDayOfMonth();
        int d2 = end.getDayOfMonth();
        if (d1 == 31) d1 = 30;
        if (d2 == 31 && d1 == 30) d2 = 30;
        return (end.getYear() - start.getYear()) * 360
                + (end.getMonthValue() - start.getMonthValue()) * 30
                + (d2 - d1);
    }
}
