package com.bonddesk.exchange;

/**
 * Observes matching-engine events for one book. The market-data feed and the microstructure
 * analytics subscribe here — every trade, rest and cancel flows through these callbacks, so
 * downstream consumers see exactly what the engine did, in order. Called on the engine thread, so
 * implementations must be cheap and non-blocking (hand off to a queue for anything heavy).
 */
public interface ExchangeListener {

    default void onAccepted(Order order) {}

    default void onRejected(long orderId, String participant, String reason) {}

    default void onResting(Order order) {}

    default void onTrade(Trade trade) {}

    default void onCancelled(Order order) {}

    /** An in-place amend (size reduction keeping time priority); the order's remaining qty shrank. */
    default void onReplaced(Order order) {}

    ExchangeListener NOOP = new ExchangeListener() {};
}
