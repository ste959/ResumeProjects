package com.bonddesk.oms.risk;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.service.PositionService;
import com.bonddesk.oms.util.Pricing;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.Optional;

/**
 * Aggregate pre-trade risk guard for the live order path. Where {@code ComplianceService}
 * vets a single order against per-order/per-security rules, this checks the order against the
 * portfolio's <em>aggregate</em> exposure: it rejects an order that would push the portfolio's
 * total gross notional (existing open positions plus this order) over the desk limit.
 *
 * <p>This makes an aggregate breaker part of live order entry — previously the only aggregate
 * kill-switch lived in {@code BacktestService}, so live flow had no aggregate protection.
 */
@Service
public class PreTradeRiskGuard {

    private final PositionService positions;
    private final RiskLimitProperties limits;

    public PreTradeRiskGuard(PositionService positions, RiskLimitProperties limits) {
        this.positions = positions;
        this.limits = limits;
    }

    /**
     * Evaluate the incoming order against the aggregate gross-notional limit for its portfolio.
     * Returns a breach reason if the order would exceed the limit, or empty if it is within
     * bounds (or the limit is disabled).
     */
    public Optional<String> check(Order order) {
        BigDecimal max = limits.getMaxGrossNotional();
        if (max == null || max.signum() <= 0) {
            return Optional.empty(); // aggregate check disabled
        }

        BigDecimal existingGross = BigDecimal.ZERO;
        for (Position p : positions.forPortfolio(order.getPortfolio())) {
            BigDecimal net = p.getNetQuantity();
            if (net == null || net.signum() == 0) {
                continue;
            }
            existingGross = existingGross.add(
                    Pricing.notional(p.getSecurity(), net.abs(), p.getSecurity().getCleanPrice()).abs());
        }

        BigDecimal projected = existingGross.add(Pricing.notional(order).abs());
        if (projected.compareTo(max) > 0) {
            return Optional.of(String.format(
                    "Aggregate gross notional %s for portfolio %s would breach the desk limit %s",
                    projected.toPlainString(), order.getPortfolio(), max.toPlainString()));
        }
        return Optional.empty();
    }
}
