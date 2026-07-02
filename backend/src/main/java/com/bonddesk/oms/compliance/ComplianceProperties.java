package com.bonddesk.oms.compliance;

import com.bonddesk.oms.domain.CreditRating;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.math.BigDecimal;

/**
 * Externalised compliance limits, bound from the {@code compliance.*} keys in
 * application.yml so the desk's risk parameters can be tuned without a recompile.
 */
@ConfigurationProperties(prefix = "compliance")
public class ComplianceProperties {

    /** Maximum market-value notional for a single order. */
    private BigDecimal maxOrderNotional = new BigDecimal("25000000");

    /** Maximum absolute market-value exposure to one security within a portfolio. */
    private BigDecimal maxSecurityNotionalPerPortfolio = new BigDecimal("50000000");

    /** Weakest credit rating the desk is allowed to trade. */
    private CreditRating minRating = CreditRating.BB_MINUS;

    public BigDecimal getMaxOrderNotional() {
        return maxOrderNotional;
    }

    public void setMaxOrderNotional(BigDecimal maxOrderNotional) {
        this.maxOrderNotional = maxOrderNotional;
    }

    public BigDecimal getMaxSecurityNotionalPerPortfolio() {
        return maxSecurityNotionalPerPortfolio;
    }

    public void setMaxSecurityNotionalPerPortfolio(BigDecimal maxSecurityNotionalPerPortfolio) {
        this.maxSecurityNotionalPerPortfolio = maxSecurityNotionalPerPortfolio;
    }

    public CreditRating getMinRating() {
        return minRating;
    }

    public void setMinRating(CreditRating minRating) {
        this.minRating = minRating;
    }
}
