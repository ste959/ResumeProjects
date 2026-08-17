package com.bonddesk.oms.exception;

/**
 * Thrown when an {@code Idempotency-Key} is reused with a different request body — a client mistake that
 * must not silently return the original resource. Maps to HTTP 422 (Unprocessable Entity).
 */
public class IdempotencyMismatchException extends RuntimeException {
    public IdempotencyMismatchException(String message) {
        super(message);
    }
}
