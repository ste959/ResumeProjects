package com.bonddesk.rates;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Our dealing desk's book — net positions (in $mm face, signed) across the bond universe — and its
 * risk, valued off a curve + per-name credit spreads. Everything is in dollars: a position of P $mm
 * at a price move of one price point is P·$10,000, and a $ DV01 is that scaled by the bond's DV01.
 */
public final class RatesBook {

    private final Map<String, Double> positions = new LinkedHashMap<>();

    /** Book a filled RFQ: as the dealer, a client BUY means we sold (position falls). */
    public void trade(String instrument, boolean clientBuys, double sizeMM) {
        positions.merge(instrument, clientBuys ? -sizeMM : sizeMM, Double::sum);
    }

    public double position(String instrument) {
        return positions.getOrDefault(instrument, 0.0);
    }

    public Map<String, Double> positions() {
        return new HashMap<>(positions);
    }

    /** Mark-to-market value of the book in dollars. */
    public double valueUsd(Map<String, Bond> bonds, RateCurve curve, Map<String, Double> spreads) {
        double v = 0;
        for (var e : positions.entrySet()) {
            Bond b = bonds.get(e.getKey());
            if (b == null) continue;
            v += e.getValue() * BondMath.price(b, curve, spreads.getOrDefault(e.getKey(), 0.0)) * 1e4;
        }
        return v;
    }

    /** Net $ DV01 of the book (dollars per 1bp parallel curve move). */
    public double dv01Usd(Map<String, Bond> bonds, RateCurve curve, Map<String, Double> spreads) {
        double d = 0;
        for (var e : positions.entrySet()) {
            Bond b = bonds.get(e.getKey());
            if (b == null) continue;
            d += e.getValue() * BondMath.dv01(b, curve, spreads.getOrDefault(e.getKey(), 0.0)) * 1e4;
        }
        return d;
    }

    /** Net $ key-rate DV01 of the book, bucketed by curve pillar (dollars per 1bp of that pillar). */
    public double[] keyRateDv01Usd(Map<String, Bond> bonds, RateCurve curve, Map<String, Double> spreads) {
        double[] agg = new double[curve.pillarCount()];
        for (var e : positions.entrySet()) {
            Bond b = bonds.get(e.getKey());
            if (b == null) continue;
            double[] kr = BondMath.keyRateDv01(b, curve, spreads.getOrDefault(e.getKey(), 0.0));
            for (int k = 0; k < agg.length; k++) {
                agg[k] += e.getValue() * kr[k] * 1e4;
            }
        }
        return agg;
    }
}
