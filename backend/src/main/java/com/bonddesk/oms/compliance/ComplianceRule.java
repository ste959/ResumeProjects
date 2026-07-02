package com.bonddesk.oms.compliance;

import com.bonddesk.oms.domain.Order;

import java.util.Optional;

/**
 * A single pre-trade compliance check. Implementations are discovered as Spring beans
 * and run by {@link ComplianceService}, so adding a new rule is just adding a class —
 * no existing code changes. This is the Strategy pattern applied to trade surveillance.
 */
public interface ComplianceRule {

    /** Short stable identifier for logging/audit, e.g. "MAX_ORDER_NOTIONAL". */
    String code();

    /**
     * @return a violation message if this rule is breached, otherwise empty.
     */
    Optional<String> evaluate(Order order);
}
