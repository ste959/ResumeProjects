package com.bonddesk.oms.dto;

import com.bonddesk.oms.domain.Execution;

import java.math.BigDecimal;
import java.time.Instant;

public record ExecutionResponse(
        Long id,
        BigDecimal quantity,
        BigDecimal price,
        String venue,
        Instant executedAt
) {

    public static ExecutionResponse from(Execution e) {
        return new ExecutionResponse(e.getId(), e.getQuantity(), e.getPrice(), e.getVenue(), e.getExecutedAt());
    }
}
