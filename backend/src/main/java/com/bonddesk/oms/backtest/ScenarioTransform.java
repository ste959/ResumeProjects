package com.bonddesk.oms.backtest;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;

/**
 * A counterfactual transform applied to a recorded L2 stream during replay: it perturbs the
 * market into a different regime while preserving book structure, so the <em>same</em> strategy
 * can be re-run against a harder or easier world. If an edge only survives on the exact recorded
 * path, it is overfit; if it survives across regimes, it is robust.
 *
 * <p>Prices are decomposed around two smoothed anchors of the traded price — a slow mean and a
 * faster mid — so volatility (how far the mid wanders from the mean) and spread (how far quotes
 * sit from the mid) can be scaled independently, without scrambling price-time order. Because the
 * transform is monotonic in price at any instant, bids stay below the mid and asks above it.
 */
public final class ScenarioTransform {

    private static final double ALPHA_MID = 0.05;
    private static final double ALPHA_MEAN = 0.005;

    private final double volScale;
    private final double spreadScale;
    private final double liquidityScale;
    private final double driftBpsPerMin;
    private final double shockBps;
    private final long shockAtSecond;

    private Instant start;
    private double refMid;
    private double refMean;
    private boolean seeded;

    public ScenarioTransform(double volScale, double spreadScale, double liquidityScale,
                             double driftBpsPerMin, double shockBps, long shockAtSecond) {
        // Clamp scales to sane, non-degenerate ranges (a 0 spread would collapse the book).
        this.volScale = clamp(volScale, 0.1, 10.0);
        this.spreadScale = clamp(spreadScale, 0.1, 10.0);
        this.liquidityScale = clamp(liquidityScale, 0.01, 100.0);
        this.driftBpsPerMin = driftBpsPerMin;
        this.shockBps = shockBps;
        this.shockAtSecond = shockAtSecond;
    }

    public void start(Instant t) {
        this.start = t;
    }

    public L2Event apply(L2Event e) {
        double rawPrice = e.price().doubleValue();
        if (e.isTrade()) {
            if (!seeded) {
                refMid = rawPrice;
                refMean = rawPrice;
                seeded = true;
            } else {
                refMid += ALPHA_MID * (rawPrice - refMid);
                refMean += ALPHA_MEAN * (rawPrice - refMean);
            }
        }

        double price = rawPrice;
        if (seeded && (volScale != 1.0 || spreadScale != 1.0)) {
            double ampMid = refMean + volScale * (refMid - refMean);   // scale the mid's excursion
            price = ampMid + spreadScale * (rawPrice - refMid);        // scale distance from mid
        }
        if (start != null && driftBpsPerMin != 0) {
            double minutes = Duration.between(start, e.ts()).toMillis() / 60_000.0;
            price *= 1 + driftBpsPerMin / 10_000.0 * minutes;
        }
        if (start != null && shockBps != 0 && shockAtSecond > 0
                && Duration.between(start, e.ts()).getSeconds() >= shockAtSecond) {
            price *= 1 + shockBps / 10_000.0;
        }
        if (price <= 0) {
            price = rawPrice; // never invert a price
        }

        double size = Math.max(0, e.size().doubleValue() * liquidityScale);

        return new L2Event(e.seq(), e.ts(), e.product(), e.kind(), e.side(),
                BigDecimal.valueOf(price), BigDecimal.valueOf(size));
    }

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}
