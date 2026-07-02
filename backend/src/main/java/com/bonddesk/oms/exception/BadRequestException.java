package com.bonddesk.oms.exception;

/** Thrown for semantically invalid requests (e.g. a LIMIT order with no price). Maps to HTTP 400. */
public class BadRequestException extends RuntimeException {
    public BadRequestException(String message) {
        super(message);
    }
}
