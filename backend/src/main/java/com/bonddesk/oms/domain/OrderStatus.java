package com.bonddesk.oms.domain;

import java.util.Set;

/**
 * Lifecycle states of a fixed-income order.
 *
 * <p>The legal transitions are encoded on each state so the {@code OrderService}
 * can enforce the workflow rather than scattering {@code if} checks across the code:
 *
 * <pre>
 *   NEW ─▶ STAGED ─▶ ROUTED ─▶ PARTIALLY_FILLED ─▶ FILLED
 *    │        │         │              │
 *    └────────┴─────────┴──────────────┴──▶ CANCELLED
 *   NEW ─▶ REJECTED   (failed compliance at entry)
 * </pre>
 */
public enum OrderStatus {
    /** Created but not yet released by the trader. */
    NEW,
    /** Released by the trader and awaiting routing. */
    STAGED,
    /** Sent to an execution venue; working in the market. */
    ROUTED,
    /** Some quantity filled, remainder still working. */
    PARTIALLY_FILLED,
    /** Fully executed. Terminal. */
    FILLED,
    /** Cancelled before completion. Terminal. */
    CANCELLED,
    /** Rejected at entry (e.g. compliance breach). Terminal. */
    REJECTED;

    /** States from which this order can no longer change. */
    public static final Set<OrderStatus> TERMINAL = Set.of(FILLED, CANCELLED, REJECTED);

    public boolean isTerminal() {
        return TERMINAL.contains(this);
    }

    /**
     * @return the set of states this order may legally move to next.
     */
    public Set<OrderStatus> allowedTransitions() {
        return switch (this) {
            case NEW -> Set.of(STAGED, CANCELLED, REJECTED);
            case STAGED -> Set.of(ROUTED, CANCELLED);
            case ROUTED -> Set.of(PARTIALLY_FILLED, FILLED, CANCELLED);
            case PARTIALLY_FILLED -> Set.of(FILLED, CANCELLED);
            case FILLED, CANCELLED, REJECTED -> Set.of();
        };
    }

    public boolean canTransitionTo(OrderStatus target) {
        return allowedTransitions().contains(target);
    }
}
