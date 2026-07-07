package com.bonddesk.oms.market;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * A live price-level order book for one product, maintained from Coinbase's {@code level2}
 * feed. Bids are keyed high-to-low and asks low-to-high, so the best of each side is the
 * first entry. Backed by {@link ConcurrentSkipListMap} so the feed thread can apply
 * updates while request threads read a weakly-consistent view.
 *
 * <p>The two sides live together behind one {@code volatile} {@link Sides} holder so a
 * snapshot replace ({@link #resetTo}) can swap in a fully-built book atomically. Every read
 * captures the holder once, so a reader always sees one internally consistent book — never an
 * empty or crossed intermediate state while a snapshot is being applied.
 */
public final class LiveOrderBook {

    /** [price, size] pair for a depth level. */
    public record Level(BigDecimal price, BigDecimal size) {}

    /** The two book sides, swapped as a unit on a snapshot replace. */
    private record Sides(ConcurrentSkipListMap<BigDecimal, BigDecimal> bids,
                         ConcurrentSkipListMap<BigDecimal, BigDecimal> asks) {}

    private final String product;
    private volatile Sides sides = emptySides();
    // Monotonic count of feed events applied — a real throughput signal for the live stream
    // (the broadcaster diffs it each tick to report book updates/sec). Incremented on the feed thread.
    private final AtomicLong updates = new AtomicLong();
    private volatile long lastUpdateMillis;

    public LiveOrderBook(String product) {
        this.product = product;
    }

    /** Total feed events applied to this book since start (snapshot replaces + increments). */
    public long updateCount() {
        return updates.get();
    }

    /** Wall-clock millis of the most recent feed event (0 if none yet) — for a book-age/latency read. */
    public long lastUpdateMillis() {
        return lastUpdateMillis;
    }

    private static Sides emptySides() {
        return new Sides(new ConcurrentSkipListMap<>(Collections.reverseOrder()),
                new ConcurrentSkipListMap<>());
    }

    public String product() {
        return product;
    }

    /** Replace the entire book (a fresh snapshot). Built fully off to the side, then swapped
     * in atomically so readers never observe a half-cleared or crossed book. */
    public void resetTo(List<Level> bidLevels, List<Level> askLevels) {
        Sides next = emptySides();
        bidLevels.forEach(l -> next.bids().put(l.price(), l.size()));
        askLevels.forEach(l -> next.asks().put(l.price(), l.size()));
        sides = next;
        touch();
    }

    /** Apply one incremental change; size 0 removes the level. */
    public void apply(boolean bid, BigDecimal price, BigDecimal size) {
        Sides s = sides;
        ConcurrentSkipListMap<BigDecimal, BigDecimal> side = bid ? s.bids() : s.asks();
        if (size.signum() <= 0) {
            side.remove(price);
        } else {
            side.put(price, size);
        }
        touch();
    }

    private void touch() {
        updates.incrementAndGet();
        lastUpdateMillis = System.currentTimeMillis();
    }

    public BigDecimal bestBid() {
        Map.Entry<BigDecimal, BigDecimal> e = sides.bids().firstEntry();
        return e == null ? null : e.getKey();
    }

    public BigDecimal bestAsk() {
        Map.Entry<BigDecimal, BigDecimal> e = sides.asks().firstEntry();
        return e == null ? null : e.getKey();
    }

    public BigDecimal bestBidSize() {
        Map.Entry<BigDecimal, BigDecimal> e = sides.bids().firstEntry();
        return e == null ? null : e.getValue();
    }

    public BigDecimal bestAskSize() {
        Map.Entry<BigDecimal, BigDecimal> e = sides.asks().firstEntry();
        return e == null ? null : e.getValue();
    }

    /** Size-weighted fair value: leans toward the side with more size behind it. */
    public BigDecimal microprice() {
        Sides s = sides; // one consistent view of both sides
        Map.Entry<BigDecimal, BigDecimal> b = s.bids().firstEntry();
        Map.Entry<BigDecimal, BigDecimal> a = s.asks().firstEntry();
        if (b == null || a == null) {
            return null;
        }
        BigDecimal bid = b.getKey(), ask = a.getKey(), bs = b.getValue(), as = a.getValue();
        BigDecimal denom = bs.add(as);
        if (denom.signum() == 0) {
            return midOf(bid, ask);
        }
        // microprice = (bid*askSize + ask*bidSize) / (bidSize + askSize)
        return bid.multiply(as).add(ask.multiply(bs)).divide(denom, 8, java.math.RoundingMode.HALF_UP);
    }

    public BigDecimal mid() {
        Sides s = sides; // read both sides from one consistent view
        Map.Entry<BigDecimal, BigDecimal> b = s.bids().firstEntry();
        Map.Entry<BigDecimal, BigDecimal> a = s.asks().firstEntry();
        return (b == null || a == null) ? null : midOf(b.getKey(), a.getKey());
    }

    private static BigDecimal midOf(BigDecimal b, BigDecimal a) {
        return b.add(a).divide(BigDecimal.valueOf(2));
    }

    /** Top {@code depth} levels of a side, best first. */
    public List<Level> depth(boolean bid, int depth) {
        ConcurrentSkipListMap<BigDecimal, BigDecimal> side = bid ? sides.bids() : sides.asks();
        List<Level> rows = new ArrayList<>(depth);
        for (Map.Entry<BigDecimal, BigDecimal> e : side.entrySet()) {
            if (rows.size() >= depth) break;
            rows.add(new Level(e.getKey(), e.getValue()));
        }
        return rows;
    }

    /**
     * Resting size at exactly {@code price} on the given side, or zero if that level is
     * empty. This is the size ahead of a new order joining at {@code price} in time
     * priority — the correct queue-ahead measure, since any trade that reaches your price
     * has already consumed the better-priced levels. (Contrast {@link #sizeAtOrBetter},
     * which includes better levels and therefore over-counts the queue.)
     */
    public BigDecimal sizeAt(boolean bid, BigDecimal price) {
        Sides s = sides;
        BigDecimal size = (bid ? s.bids() : s.asks()).get(price);
        return size == null ? BigDecimal.ZERO : size;
    }

    /**
     * Total resting size at prices at least as good as {@code price} on the given side —
     * i.e. all size that would fill before an order at {@code price}. Retained for depth
     * queries; for queue position prefer {@link #sizeAt}.
     */
    public BigDecimal sizeAtOrBetter(boolean bid, BigDecimal price) {
        ConcurrentSkipListMap<BigDecimal, BigDecimal> side = bid ? sides.bids() : sides.asks();
        BigDecimal total = BigDecimal.ZERO;
        for (Map.Entry<BigDecimal, BigDecimal> e : side.entrySet()) {
            boolean atOrBetter = bid ? e.getKey().compareTo(price) >= 0 : e.getKey().compareTo(price) <= 0;
            if (!atOrBetter) {
                break; // levels are best-first, so once worse than price we can stop
            }
            total = total.add(e.getValue());
        }
        return total;
    }

    /** A point-in-time copy of one side (best first) for matching a paper order. */
    public List<Level> snapshot(boolean bid) {
        ConcurrentSkipListMap<BigDecimal, BigDecimal> side = bid ? sides.bids() : sides.asks();
        List<Level> rows = new ArrayList<>(side.size());
        side.forEach((price, size) -> rows.add(new Level(price, size)));
        return rows;
    }

    public boolean isReady() {
        return bestBid() != null && bestAsk() != null;
    }
}
