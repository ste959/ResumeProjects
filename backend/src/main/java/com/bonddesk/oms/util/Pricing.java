package com.bonddesk.oms.util;

import com.bonddesk.oms.domain.Order;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Shared bond math. Bond prices are quoted as a percentage of par, so the cash
 * consideration (notional) for a trade is {@code faceQuantity * price / 100}.
 */
public final class Pricing {

    private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

    private Pricing() {
    }

    /**
     * Best available price estimate for an order: its limit price if one was given,
     * otherwise the security's latest indicative clean price.
     */
    public static BigDecimal referencePrice(Order order) {
        return order.getLimitPrice() != null
                ? order.getLimitPrice()
                : order.getSecurity().getCleanPrice();
    }

    /** Cash consideration for {@code faceQuantity} of par at {@code price} (% of par). */
    public static BigDecimal notional(BigDecimal faceQuantity, BigDecimal price) {
        return faceQuantity.multiply(price)
                .divide(HUNDRED, 2, RoundingMode.HALF_UP);
    }
}
