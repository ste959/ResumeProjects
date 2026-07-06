package com.bonddesk.oms.compliance.rules;

import com.bonddesk.oms.compliance.ComplianceProperties;
import com.bonddesk.oms.compliance.ComplianceRule;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.util.Pricing;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.util.Optional;

/** Blocks a single order whose cash notional exceeds the configured per-order cap. */
@Component
public class MaxOrderNotionalRule implements ComplianceRule {

    private static final DecimalFormat MONEY = new DecimalFormat("#,##0");

    private final ComplianceProperties props;

    public MaxOrderNotionalRule(ComplianceProperties props) {
        this.props = props;
    }

    @Override
    public String code() {
        return "MAX_ORDER_NOTIONAL";
    }

    @Override
    public Optional<String> evaluate(Order order) {
        BigDecimal notional = Pricing.notional(order);
        if (notional.compareTo(props.getMaxOrderNotional()) > 0) {
            return Optional.of("Order notional %s exceeds the per-order limit of %s"
                    .formatted(MONEY.format(notional), MONEY.format(props.getMaxOrderNotional())));
        }
        return Optional.empty();
    }
}
