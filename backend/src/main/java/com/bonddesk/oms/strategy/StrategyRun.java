package com.bonddesk.oms.strategy;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

/** Mutable state of one running strategy instance. */
public final class StrategyRun {

    private static final AtomicLong SEQ = new AtomicLong();

    private final String id = "s" + SEQ.incrementAndGet();
    private final String type;
    private final String product;
    private final Strategy strategy;
    private final PnlBook book = new PnlBook();
    private final Instant createdAt;

    private volatile String status = "RUNNING";
    private volatile double arrivalMid;      // benchmark for execution TCA
    private volatile Instant updatedAt;

    // Maker quotes currently resting (per tick).
    private volatile double quoteBid;
    private volatile double quoteAsk;
    private volatile double quoteSize;
    private long lastTradeSeq = -1;

    // Execution TCA accumulators + parent-order metadata.
    private volatile double executedSize;
    private volatile double executedNotional;
    private volatile String parentSide;   // "BUY"/"SELL" for execution algos; null for MM
    private volatile double parentSize;

    public String parentSide() { return parentSide; }
    public double parentSize() { return parentSize; }
    public void setParent(String side, double size) { this.parentSide = side; this.parentSize = size; }

    public StrategyRun(String type, String product, Strategy strategy, Instant now) {
        this.type = type;
        this.product = product;
        this.strategy = strategy;
        this.createdAt = now;
        this.updatedAt = now;
    }

    public String id() { return id; }
    public String type() { return type; }
    public String product() { return product; }
    public Strategy strategy() { return strategy; }
    public PnlBook book() { return book; }
    public Instant createdAt() { return createdAt; }
    public Instant updatedAt() { return updatedAt; }
    public void touch(Instant t) { this.updatedAt = t; }

    public String status() { return status; }
    public void setStatus(String status) { this.status = status; }
    public boolean isActive() { return "RUNNING".equals(status); }

    public double arrivalMid() { return arrivalMid; }
    public void setArrivalMid(double m) { this.arrivalMid = m; }

    public double quoteBid() { return quoteBid; }
    public double quoteAsk() { return quoteAsk; }
    public double quoteSize() { return quoteSize; }

    public void setQuotes(double bid, double ask, double size) {
        this.quoteBid = bid;
        this.quoteAsk = ask;
        this.quoteSize = size;
    }

    public void reduceQuote(double filled) {
        this.quoteSize = Math.max(0, this.quoteSize - filled);
    }

    public long lastTradeSeq() { return lastTradeSeq; }
    public void setLastTradeSeq(long seq) { this.lastTradeSeq = seq; }

    public double executedSize() { return executedSize; }
    public double executedNotional() { return executedNotional; }

    public void recordExecuted(double size, double notional) {
        this.executedSize += size;
        this.executedNotional += notional;
    }
}
