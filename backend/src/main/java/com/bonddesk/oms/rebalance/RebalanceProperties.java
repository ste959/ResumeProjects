package com.bonddesk.oms.rebalance;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.math.BigDecimal;

/**
 * Configuration for the equity rebalance path, bound from {@code oms.rebalance.*}.
 *
 * <p>The feature is <b>disabled by default</b> ({@code enabled=false}) and its controller is
 * gated on this flag, so the rebalance endpoint cannot be triggered accidentally — this is
 * execution-infrastructure validation against a paper venue, not a live strategy.
 */
@ConfigurationProperties(prefix = "oms.rebalance")
public class RebalanceProperties {

    /** Master switch. When false the rebalance controller is not even registered. */
    private boolean enabled = false;

    /** Notional the unit-gross target weights are scaled to, in dollars. */
    private BigDecimal grossCapital = new BigDecimal("100000");

    /** Portfolio the rebalance reads positions from and books orders into. */
    private String portfolio = "EQUITY-PAPER";

    /** Path to the research target-book JSON, relative to the working directory. */
    private String targetBookPath = "target-book/target-book.json";

    /** Rebalance-specific projected-gross-notional cap ($). Kept tight for the paper equity book,
     * independent of and tighter than the desk-wide {@code oms.risk.max-gross-notional} — so the
     * equity book is on a short leash without lowering the desk cap below the bond side's per-order
     * compliance. The rebalance is gated on the TIGHTER of the two. */
    private BigDecimal maxGrossNotional = new BigDecimal("250000");

    public BigDecimal getMaxGrossNotional() {
        return maxGrossNotional;
    }

    public void setMaxGrossNotional(BigDecimal maxGrossNotional) {
        this.maxGrossNotional = maxGrossNotional;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public BigDecimal getGrossCapital() {
        return grossCapital;
    }

    public void setGrossCapital(BigDecimal grossCapital) {
        this.grossCapital = grossCapital;
    }

    public String getPortfolio() {
        return portfolio;
    }

    public void setPortfolio(String portfolio) {
        this.portfolio = portfolio;
    }

    public String getTargetBookPath() {
        return targetBookPath;
    }

    public void setTargetBookPath(String targetBookPath) {
        this.targetBookPath = targetBookPath;
    }
}
