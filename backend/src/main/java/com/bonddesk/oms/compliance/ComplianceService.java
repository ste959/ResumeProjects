package com.bonddesk.oms.compliance;

import com.bonddesk.oms.domain.Order;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * Runs an order through every registered {@link ComplianceRule} and aggregates the
 * breaches. Spring injects the full list of rule beans, so the surveillance policy is
 * simply "whatever rules exist on the classpath" — new checks compose in automatically.
 */
@Service
public class ComplianceService {

    private static final Logger log = LoggerFactory.getLogger(ComplianceService.class);

    private final List<ComplianceRule> rules;

    public ComplianceService(List<ComplianceRule> rules) {
        this.rules = rules;
        log.info("Compliance engine initialised with {} rule(s): {}",
                rules.size(), rules.stream().map(ComplianceRule::code).toList());
    }

    /**
     * Evaluate every rule against the order. All rules run (rather than short-circuiting)
     * so the trader sees every breach at once instead of fixing them one at a time.
     */
    public ComplianceResult check(Order order) {
        List<String> violations = new ArrayList<>();
        for (ComplianceRule rule : rules) {
            rule.evaluate(order).ifPresent(msg -> {
                log.debug("Compliance breach [{}] on order {}: {}", rule.code(), order.getOrderRef(), msg);
                violations.add(msg);
            });
        }
        return violations.isEmpty() ? ComplianceResult.approve() : ComplianceResult.reject(violations);
    }
}
