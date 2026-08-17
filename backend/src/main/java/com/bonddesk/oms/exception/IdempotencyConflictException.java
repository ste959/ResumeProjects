package com.bonddesk.oms.exception;

/**
 * Thrown when a request arrives with an {@code Idempotency-Key} that a concurrent request is still
 * processing. The client should retry after a short back-off. Maps to HTTP 409.
 */
public class IdempotencyConflictException extends RuntimeException {
    public IdempotencyConflictException(String message) {
        super(message);
    }
}
