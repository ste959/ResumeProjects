package com.bonddesk.oms.compliance.rules;

import com.bonddesk.oms.compliance.ComplianceProperties;
import com.bonddesk.oms.compliance.ComplianceRule;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.repository.PositionRepository;
import com.bonddesk.oms.util.Pricing;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.util.Optional;

/**
 * Blocks an order that would push the portfolio's absolute exposure to a single
 * security beyond the configured concentration cap. Projects the post-trade position
 * by applying the order's signed quantity to the current holding.
 */
@Component
public class ConcentrationLimitRule implements ComplianceRule {

    private static final DecimalFormat MONEY = new DecimalFormat("#,##0");

    private final PositionRepository positions;
    private final ComplianceProperties props;

    public ConcentrationLimitRule(PositionRepository positions, ComplianceProperties props) {
        this.positions = positions;
        this.props = props;
    }

    @Override
    public String code() {
        return "CONCENTRATION_LIMIT";
    }

    @Override
    public Optional<String> evaluate(Order order) {
        BigDecimal currentNet = positions
                .findByPortfolioAndSecurity_Cusip(order.getPortfolio(), order.getSecurity().getCusip())
                .map(Position::getNetQuantity)
                .orElse(BigDecimal.ZERO);

        BigDecimal signedOrderQty = order.getSide() == OrderSide.BUY
                ? order.getQuantity()
                : order.getQuantity().negate();

        BigDecimal projectedNet = currentNet.add(signedOrderQty).abs();
        BigDecimal projectedNotional =
                Pricing.notional(order.getSecurity(), projectedNet, Pricing.referencePrice(order));

        if (projectedNotional.compareTo(props.getMaxSecurityNotionalPerPortfolio()) > 0) {
            return Optional.of("Post-trade exposure %s in %s for %s exceeds the concentration limit of %s"
                    .formatted(MONEY.format(projectedNotional), order.getSecurity().getCusip(),
                            order.getPortfolio(), MONEY.format(props.getMaxSecurityNotionalPerPortfolio())));
        }
        return Optional.empty();
    }
}
