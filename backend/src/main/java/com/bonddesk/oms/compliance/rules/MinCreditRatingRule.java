package com.bonddesk.oms.compliance.rules;

import com.bonddesk.oms.compliance.ComplianceProperties;
import com.bonddesk.oms.compliance.ComplianceRule;
import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.CreditRating;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Security;
import org.springframework.stereotype.Component;

import java.util.Optional;

/** Blocks BUY orders in bonds rated below the desk's configured minimum. */
@Component
public class MinCreditRatingRule implements ComplianceRule {

    private final ComplianceProperties props;

    public MinCreditRatingRule(ComplianceProperties props) {
        this.props = props;
    }

    @Override
    public String code() {
        return "MIN_CREDIT_RATING";
    }

    @Override
    public Optional<String> evaluate(Order order) {
        Security security = order.getSecurity();
        // Credit ratings only apply to fixed income; equities have no rating to check.
        if (security.getAssetClass() != AssetClass.FIXED_INCOME || security.getRating() == null) {
            return Optional.empty();
        }
        // Selling out of a downgraded name is allowed; only buying more is blocked.
        if (order.getSide() == OrderSide.SELL) {
            return Optional.empty();
        }
        CreditRating rating = security.getRating();
        CreditRating floor = props.getMinRating();
        if (!rating.isAtLeast(floor)) {
            return Optional.of("Rating %s is below the desk minimum of %s".formatted(rating, floor));
        }
        return Optional.empty();
    }
}
