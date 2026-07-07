package com.bonddesk.exchange;

/** The side of an order on the exchange. */
public enum Side {
    BUY,
    SELL;

    public Side opposite() {
        return this == BUY ? SELL : BUY;
    }
}
