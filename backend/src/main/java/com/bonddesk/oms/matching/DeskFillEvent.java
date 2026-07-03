package com.bonddesk.oms.matching;

import java.math.BigDecimal;

/**
 * Published when a trade fills one of the desk's own orders. A Spring event decouples
 * the matching engine from persistence: the engine emits fills; a listener records them
 * against the OMS order — no direct dependency from the engine on {@code OrderService}.
 */
public record DeskFillEvent(String orderRef, BigDecimal quantity, BigDecimal price, String venue) {
}
