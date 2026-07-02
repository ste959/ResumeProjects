package com.bonddesk.oms.exception;

import com.bonddesk.oms.domain.OrderStatus;

/** Thrown when an order is asked to move to a state its lifecycle forbids. Maps to HTTP 409. */
public class InvalidStateTransitionException extends RuntimeException {
    public InvalidStateTransitionException(String orderRef, OrderStatus from, OrderStatus to) {
        super("Order %s cannot transition from %s to %s".formatted(orderRef, from, to));
    }
}
