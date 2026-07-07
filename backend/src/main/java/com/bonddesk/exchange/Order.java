package com.bonddesk.exchange;

/**
 * A resting or in-flight order inside the matching engine. Identity ({@code id}) and arrival
 * sequence ({@code seq}, which sets time priority within a price level) are stamped by the engine
 * on acceptance. Prices are integer <b>ticks</b> and quantities integer <b>lots</b> — the engine is
 * all-integer on the hot path (no floating point in matching); the display layer maps ticks/lots to
 * real prices/sizes. Mutable {@code remaining}/{@code active} are touched only on the engine thread.
 */
public final class Order {

    private final long id;
    private final long seq;
    private final String participant;
    private final Side side;
    private final OrderType type;
    private final TimeInForce tif;
    private final boolean postOnly;
    private final long priceTicks;   // ignored for MARKET
    private final long qty;
    private long remaining;
    private boolean active = true;

    Order(long id, long seq, String participant, Side side, OrderType type, TimeInForce tif,
          boolean postOnly, long priceTicks, long qty) {
        this.id = id;
        this.seq = seq;
        this.participant = participant;
        this.side = side;
        this.type = type;
        this.tif = tif;
        this.postOnly = postOnly;
        this.priceTicks = priceTicks;
        this.qty = qty;
        this.remaining = qty;
    }

    public long id() { return id; }
    public long seq() { return seq; }
    public String participant() { return participant; }
    public Side side() { return side; }
    public OrderType type() { return type; }
    public TimeInForce tif() { return tif; }
    public boolean postOnly() { return postOnly; }
    public long priceTicks() { return priceTicks; }
    public long qty() { return qty; }
    public long remaining() { return remaining; }
    public boolean isActive() { return active; }

    void reduce(long q) { remaining -= q; }
    void setRemaining(long q) { remaining = q; }
    boolean isFilled() { return remaining <= 0; }
    void deactivate() { active = false; }
}
