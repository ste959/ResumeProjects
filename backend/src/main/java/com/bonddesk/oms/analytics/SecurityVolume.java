package com.bonddesk.oms.analytics;

import java.math.BigDecimal;

/** Traded volume (filled par notional) and fill count for a single security. */
public record SecurityVolume(
        String cusip,
        String description,
        BigDecimal tradedFace,
        long fillCount
) {
}
