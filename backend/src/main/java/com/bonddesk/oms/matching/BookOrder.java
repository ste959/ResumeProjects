package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;

/**
 * An order as the matching engine sees it. Deliberately primitive and mutable: prices
 * are integer <em>ticks</em> (price × 10,000, i.e. 1/100 of a basis point of par) and
 * quantities are {@code long} face amounts, so the hot matching path does only integer
 * arithmetic and comparisons — no {@link java.math.BigDecimal}, no allocation per compare.
 *
 * <p>This type is intentionally decoupled from the JPA {@code Order} entity: the engine
 * is a self-contained library that knows nothing about persistence or Spring.
 */
public final class BookOrder {

    private final long id;
    private final OrderSide side;
    private final OrderType type;
    private final long priceTicks;   // limit price in ticks; ignored for MARKET
    private final long quantity;     // original face quantity
    private final String ownerRef;   // OMS order ref for desk orders; null for liquidity

    private long remaining;
    private boolean active = true;

    public BookOrder(long id, OrderSide side, OrderType type, long priceTicks, long quantity, String ownerRef) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        this.id = id;
        this.side = side;
        this.type = type;
        this.priceTicks = priceTicks;
        this.quantity = quantity;
        this.remaining = quantity;
        this.ownerRef = ownerRef;
    }

    public long id() { return id; }
    public OrderSide side() { return side; }
    public OrderType type() { return type; }
    public long priceTicks() { return priceTicks; }
    public long quantity() { return quantity; }
    public long remaining() { return remaining; }
    public boolean isActive() { return active; }
    public boolean isFilled() { return remaining == 0; }
    public String ownerRef() { return ownerRef; }
    public boolean isDeskOrder() { return ownerRef != null; }

    void reduce(long qty) {
        this.remaining -= qty;
        if (remaining == 0) {
            active = false;
        }
    }

    void deactivate() {
        this.active = false;
    }
}
