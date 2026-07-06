package com.bonddesk.oms.util;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.Security;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Shared trade math. The cash consideration (notional) for a trade depends on the asset
 * class: bonds are quoted as a percentage of par, so notional is
 * {@code quantity * price / 100}; equities are quoted in currency per share, so notional
 * is simply {@code shares * price}.
 */
public final class Pricing {

    private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

    private Pricing() {
    }

    /**
     * Best available price estimate for an order: its limit price if one was given,
     * otherwise the security's latest indicative reference price.
     */
    public static BigDecimal referencePrice(Order order) {
        return order.getLimitPrice() != null
                ? order.getLimitPrice()
                : order.getSecurity().getCleanPrice();
    }

    /** Cash consideration for an order at its best available reference price. */
    public static BigDecimal notional(Order order) {
        return notional(order.getSecurity(), order.getQuantity(), referencePrice(order));
    }

    /**
     * Cash consideration for {@code quantity} at {@code price}, using the asset class's
     * quoting convention: bonds divide by 100 (price is a percentage of par), equities do
     * not (price is currency per share).
     */
    public static BigDecimal notional(Security security, BigDecimal quantity, BigDecimal price) {
        BigDecimal gross = quantity.multiply(price);
        if (security.getAssetClass() == AssetClass.FIXED_INCOME) {
            gross = gross.divide(HUNDRED);
        }
        return gross.setScale(2, RoundingMode.HALF_UP);
    }
}
