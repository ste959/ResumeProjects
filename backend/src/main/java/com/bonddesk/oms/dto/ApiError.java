package com.bonddesk.oms.dto;

import java.time.Instant;
import java.util.Map;

/**
 * Consistent error body returned for every non-2xx response.
 *
 * @param fieldErrors per-field validation messages; null unless the error is a
 *                    validation failure
 */
public record ApiError(
        Instant timestamp,
        int status,
        String error,
        String message,
        String path,
        Map<String, String> fieldErrors
) {
    public static ApiError of(int status, String error, String message, String path) {
        return new ApiError(Instant.now(), status, error, message, path, null);
    }

    public static ApiError validation(int status, String message, String path, Map<String, String> fieldErrors) {
        return new ApiError(Instant.now(), status, "Bad Request", message, path, fieldErrors);
    }
}
