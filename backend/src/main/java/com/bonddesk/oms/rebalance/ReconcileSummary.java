package com.bonddesk.oms.rebalance;

/**
 * The outcome of a broker position reconciliation:
 * <ul>
 *   <li>{@code updated} — OMS positions snapped to a broker position;</li>
 *   <li>{@code flattened} — stale OMS equity positions the broker no longer holds, set to zero;</li>
 *   <li>{@code unknown} — broker symbols with no matching security in the OMS master (skipped).</li>
 * </ul>
 */
public record ReconcileSummary(int updated, int flattened, int unknown) {

    static ReconcileSummary empty() {
        return new ReconcileSummary(0, 0, 0);
    }
}
