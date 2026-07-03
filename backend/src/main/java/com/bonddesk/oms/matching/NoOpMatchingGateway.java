package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.Order;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Used when {@code oms.matching.enabled=false} (e.g. tests): routing does not go to a
 * matching engine, so fills are driven manually through the API instead.
 */
@Component
@ConditionalOnProperty(prefix = "oms.matching", name = "enabled", havingValue = "false", matchIfMissing = true)
public class NoOpMatchingGateway implements MatchingGateway {

    @Override
    public void route(Order order) {
        // no market — the order simply stays working until filled manually
    }

    @Override
    public void cancel(Order order) {
        // nothing resting in an engine to remove
    }
}
