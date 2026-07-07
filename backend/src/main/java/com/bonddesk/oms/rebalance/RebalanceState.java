package com.bonddesk.oms.rebalance;

import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.LocalDate;

/**
 * Shared, thread-safe record of the auto-rebalancer's most recent run. The scheduler writes it,
 * the ops-status endpoint reads it, and the {@code lastRunDate} enforces the once-per-trading-day
 * guard. Fields are volatile and {@link #record} publishes them together, so a concurrent read
 * from the status endpoint sees a consistent snapshot.
 */
@Component
public class RebalanceState {

    private volatile Instant lastRunTime;
    private volatile LocalDate lastRunDate;
    private volatile String status = "NEVER_RUN";
    private volatile int routed;
    private volatile int skipped;
    private volatile int rejected;

    /** Record the outcome of a completed run. */
    public synchronized void record(Instant time, LocalDate runDate, RebalanceResult result) {
        this.lastRunTime = time;
        this.lastRunDate = runDate;
        this.status = result == null ? "UNKNOWN" : result.status();
        this.routed = result == null ? 0 : result.routed();
        this.skipped = result == null ? 0 : result.skipped();
        this.rejected = result == null ? 0 : result.rejected();
    }

    public Instant lastRunTime() {
        return lastRunTime;
    }

    public LocalDate lastRunDate() {
        return lastRunDate;
    }

    public String status() {
        return status;
    }

    public int routed() {
        return routed;
    }

    public int skipped() {
        return skipped;
    }

    public int rejected() {
        return rejected;
    }
}
