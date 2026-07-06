package com.bonddesk.oms.dto;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.TimeInForce;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

/**
 * Payload for staging a new order (bond or equity). Structural validation (required
 * fields, positive quantity) is enforced here via bean validation; business rules
 * (LIMIT needs a price, compliance) are enforced in the service layer.
 *
 * <p>Quantity is in the instrument's natural unit: par face for bonds (traded in large
 * blocks), number of shares for equities.
 */
public record CreateOrderRequest(

        @NotBlank(message = "cusip is required")
        String cusip,

        @NotBlank(message = "portfolio is required")
        String portfolio,

        @NotBlank(message = "trader is required")
        String trader,

        @NotNull(message = "side is required")
        OrderSide side,

        @NotNull(message = "orderType is required")
        OrderType orderType,

        @NotNull(message = "timeInForce is required")
        TimeInForce timeInForce,

        @NotNull(message = "quantity is required")
        @DecimalMin(value = "1", message = "quantity must be at least 1")
        BigDecimal quantity,

        /** Required for LIMIT orders; ignored for MARKET orders. */
        @DecimalMin(value = "0.0", inclusive = false, message = "limitPrice must be positive")
        BigDecimal limitPrice
) {
}
