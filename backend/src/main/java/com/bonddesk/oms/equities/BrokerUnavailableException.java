package com.bonddesk.oms.equities;

/**
 * A <em>transient</em> failure talking to the broker: a connection/timeout/IO error, an HTTP 5xx, or a
 * short-circuited call while the venue's circuit breaker is open. These are worth retrying and are what
 * trips the breaker — the broker may simply be briefly unreachable. Contrast {@link BrokerRejectedException},
 * which is a terminal business rejection that retrying can never fix.
 */
public class BrokerUnavailableException extends RuntimeException {

    public BrokerUnavailableException(String message) {
        super(message);
    }

    public BrokerUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
