package com.bonddesk.oms.matching;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Converts between the OMS's {@link BigDecimal} prices/quantities and the engine's
 * integer representation. Prices are quoted as % of par to 4 dp, so one tick is
 * 1/10,000 of a point (0.0001). Quantities are whole par amounts.
 */
public final class Ticks {

    /** 1 price point = 10,000 ticks. */
    public static final long PER_POINT = 10_000L;

    private Ticks() {
    }

    public static long priceToTicks(BigDecimal price) {
        return price.movePointRight(4).setScale(0, RoundingMode.HALF_UP).longValueExact();
    }

    public static BigDecimal ticksToPrice(long ticks) {
        return BigDecimal.valueOf(ticks, 4);
    }

    public static long qtyToLong(BigDecimal qty) {
        return qty.setScale(0, RoundingMode.DOWN).longValueExact();
    }

    public static BigDecimal longToQty(long qty) {
        return BigDecimal.valueOf(qty).setScale(2);
    }
}
