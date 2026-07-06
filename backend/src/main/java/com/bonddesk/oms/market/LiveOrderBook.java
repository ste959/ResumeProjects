package com.bonddesk.oms.market;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentSkipListMap;

/**
 * A live price-level order book for one product, maintained from Coinbase's {@code level2}
 * feed. Bids are keyed high-to-low and asks low-to-high, so the best of each side is the
 * first entry. Backed by {@link ConcurrentSkipListMap} so the feed thread can apply
 * updates while request threads read a weakly-consistent view.
 */
public final class LiveOrderBook {

    /** [price, size] pair for a depth level. */
    public record Level(BigDecimal price, BigDecimal size) {}

    private final String product;
    private final ConcurrentSkipListMap<BigDecimal, BigDecimal> bids =
            new ConcurrentSkipListMap<>(Collections.reverseOrder());
    private final ConcurrentSkipListMap<BigDecimal, BigDecimal> asks =
            new ConcurrentSkipListMap<>();

    public LiveOrderBook(String product) {
        this.product = product;
    }

    public String product() {
        return product;
    }

    /** Replace the entire book (a fresh snapshot). */
    public void resetTo(List<Level> bidLevels, List<Level> askLevels) {
        bids.clear();
        asks.clear();
        bidLevels.forEach(l -> bids.put(l.price(), l.size()));
        askLevels.forEach(l -> asks.put(l.price(), l.size()));
    }

    /** Apply one incremental change; size 0 removes the level. */
    public void apply(boolean bid, BigDecimal price, BigDecimal size) {
        ConcurrentSkipListMap<BigDecimal, BigDecimal> side = bid ? bids : asks;
        if (size.signum() <= 0) {
            side.remove(price);
        } else {
            side.put(price, size);
        }
    }

    public BigDecimal bestBid() {
        Map.Entry<BigDecimal, BigDecimal> e = bids.firstEntry();
        return e == null ? null : e.getKey();
    }

    public BigDecimal bestAsk() {
        Map.Entry<BigDecimal, BigDecimal> e = asks.firstEntry();
        return e == null ? null : e.getKey();
    }

    public BigDecimal mid() {
        BigDecimal b = bestBid();
        BigDecimal a = bestAsk();
        return (b == null || a == null) ? null : b.add(a).movePointLeft(0).divide(BigDecimal.valueOf(2));
    }

    /** Top {@code depth} levels of a side, best first. */
    public List<Level> depth(boolean bid, int depth) {
        ConcurrentSkipListMap<BigDecimal, BigDecimal> side = bid ? bids : asks;
        List<Level> rows = new ArrayList<>(depth);
        for (Map.Entry<BigDecimal, BigDecimal> e : side.entrySet()) {
            if (rows.size() >= depth) break;
            rows.add(new Level(e.getKey(), e.getValue()));
        }
        return rows;
    }

    /** A point-in-time copy of one side (best first) for matching a paper order. */
    public List<Level> snapshot(boolean bid) {
        ConcurrentSkipListMap<BigDecimal, BigDecimal> side = bid ? bids : asks;
        List<Level> rows = new ArrayList<>(side.size());
        side.forEach((price, size) -> rows.add(new Level(price, size)));
        return rows;
    }

    public boolean isReady() {
        return bestBid() != null && bestAsk() != null;
    }
}
