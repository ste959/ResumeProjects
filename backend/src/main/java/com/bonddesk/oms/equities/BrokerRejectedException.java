package com.bonddesk.oms.equities;

/**
 * A <em>terminal</em> rejection from the broker: an HTTP 4xx that means the request itself was invalid or
 * not permitted (e.g. an unsupported symbol, a bad quantity, insufficient buying power). Retrying can
 * never fix it and it says nothing about the venue's health, so it is deliberately excluded from both the
 * retry policy and the circuit breaker's failure accounting. Contrast {@link BrokerUnavailableException}.
 */
public class BrokerRejectedException extends RuntimeException {

    public BrokerRejectedException(String message) {
        super(message);
    }
}
