package com.bonddesk.oms.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

/** Manually report a fill against a working order (also used to drive tests). */
public record FillRequest(

        @NotNull(message = "quantity is required")
        @DecimalMin(value = "0.0", inclusive = false, message = "quantity must be positive")
        BigDecimal quantity,

        @NotNull(message = "price is required")
        @DecimalMin(value = "0.0", inclusive = false, message = "price must be positive")
        BigDecimal price,

        String venue
) {
    public String venueOrDefault() {
        return venue == null || venue.isBlank() ? "MANUAL" : venue;
    }
}
