package com.bonddesk.oms.compliance;

import java.util.List;

/**
 * Outcome of running an order through the compliance rule set.
 *
 * @param approved   true when no rule was breached
 * @param violations human-readable breach messages (empty when approved)
 */
public record ComplianceResult(boolean approved, List<String> violations) {

    public static ComplianceResult approve() {
        return new ComplianceResult(true, List.of());
    }

    public static ComplianceResult reject(List<String> violations) {
        return new ComplianceResult(false, List.copyOf(violations));
    }

    /** Joined breach summary suitable for an order's statusReason. */
    public String summary() {
        return String.join("; ", violations);
    }
}
