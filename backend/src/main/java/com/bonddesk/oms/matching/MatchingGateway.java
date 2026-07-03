package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.Order;

/**
 * Seam between the OMS order lifecycle and the matching engine. {@code OrderService}
 * depends only on this interface, so the engine can be switched off (tests, or a
 * "no market" mode) by swapping the implementation — no lifecycle code changes.
 */
public interface MatchingGateway {

    /** Submit a routed order to its instrument's book; fills are reported asynchronously. */
    void route(Order order);

    /** Remove a working order from its book if it is still resting. */
    void cancel(Order order);
}
