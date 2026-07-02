package com.bonddesk.oms.compliance.rules;

import com.bonddesk.oms.compliance.ComplianceRule;
import com.bonddesk.oms.domain.Order;
import org.springframework.stereotype.Component;

import java.util.Optional;

/** Blocks any order in a security flagged on the desk's restricted list. */
@Component
public class RestrictedSecurityRule implements ComplianceRule {

    @Override
    public String code() {
        return "RESTRICTED_SECURITY";
    }

    @Override
    public Optional<String> evaluate(Order order) {
        if (order.getSecurity().isRestricted()) {
            return Optional.of("Security %s (%s) is on the restricted list"
                    .formatted(order.getSecurity().getCusip(), order.getSecurity().getDescription()));
        }
        return Optional.empty();
    }
}
