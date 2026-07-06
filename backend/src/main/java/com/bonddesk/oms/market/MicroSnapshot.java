package com.bonddesk.oms.market;

/**
 * A per-second microstructure sample for the signals view.
 *
 * @param imbalance      top-of-book size imbalance in [-1, 1] (bid-heavy is positive)
 * @param microPremiumBps microprice premium over mid, in basis points (a fair-value tilt)
 */
public record MicroSnapshot(
        long epochMillis,
        double mid,
        double microprice,
        double imbalance,
        double spreadBps,
        double microPremiumBps
) {
}
