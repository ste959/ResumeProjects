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

    /** Master switch for the market-hours auto-rebalancer scheduler. DISABLED by default:
     * even with the module enabled, the scheduler is inert until this is explicitly turned on. */
    private boolean autoEnabled = false;

    /** When true, snap OMS positions to the broker's truth on startup (and before each auto run).
     * DISABLED by default so the reconciler never mutates positions unless explicitly requested. */
    private boolean reconcilePositions = false;

    /** How often the auto-rebalancer wakes to check market hours / once-per-day guard, in ms. */
    private long checkIntervalMs = 300000;

    /** True only when BOTH the module is enabled and the auto-rebalancer is switched on. */
    public boolean isAutoEnabled() {
        return enabled && autoEnabled;
    }

    public boolean getAutoEnabled() {
        return autoEnabled;
    }

    public void setAutoEnabled(boolean autoEnabled) {
        this.autoEnabled = autoEnabled;
    }

    public boolean isReconcilePositions() {
        return reconcilePositions;
    }

    public void setReconcilePositions(boolean reconcilePositions) {
        this.reconcilePositions = reconcilePositions;
    }

    public long getCheckIntervalMs() {
        return checkIntervalMs;
    }

    public void setCheckIntervalMs(long checkIntervalMs) {
        this.checkIntervalMs = checkIntervalMs;
    }

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
