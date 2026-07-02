package com.bonddesk.oms.exception;

/** Thrown when a referenced entity (order, security, position) does not exist. Maps to HTTP 404. */
public class NotFoundException extends RuntimeException {
    public NotFoundException(String message) {
        super(message);
    }
}
