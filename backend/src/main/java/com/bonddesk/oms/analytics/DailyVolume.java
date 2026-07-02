package com.bonddesk.oms.analytics;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * Traded volume for a single day plus the running cumulative total, produced with a
 * SQL window function.
 */
public record DailyVolume(
        LocalDate tradeDate,
        BigDecimal dailyFace,
        BigDecimal cumulativeFace
) {
}
