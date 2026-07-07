package com.bonddesk.oms.risk;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.math.BigDecimal;

/**
 * Live pre-trade risk limits, bound from the {@code oms.risk.*} keys in application.yml.
 * Unlike compliance (which vets a single order in isolation), these are <em>aggregate</em>
 * limits on the portfolio as a whole, enforced on the live order-entry path so the desk's
 * kill-switch protection is not backtest-only.
 */
@ConfigurationProperties(prefix = "oms.risk")
public class RiskLimitProperties {

    /**
     * Maximum aggregate gross notional — the sum of {@code |position notional|} across a
     * portfolio's open positions plus the incoming order — allowed on the live order path.
     * A non-positive value (or null) disables the aggregate check.
     */
    private BigDecimal maxGrossNotional = new BigDecimal("1000000000"); // $1bn desk-wide default

    public BigDecimal getMaxGrossNotional() {
        return maxGrossNotional;
    }

    public void setMaxGrossNotional(BigDecimal maxGrossNotional) {
        this.maxGrossNotional = maxGrossNotional;
    }
}
