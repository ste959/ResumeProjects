package com.bonddesk.oms.strategy;

/**
 * Base for schedule-driven execution algorithms: work a parent order of {@code totalSize}
 * down to zero over {@code slices} engine ticks, taking liquidity each slice. The final
 * slice always sweeps whatever remains so the parent completes.
 */
public abstract class ExecutionStrategy implements Strategy {

    protected final boolean buy;
    protected final double totalSize;
    protected final int slices;
    protected double remaining;
    protected int sliceIndex;

    protected ExecutionStrategy(boolean buy, double totalSize, int slices) {
        this.buy = buy;
        this.totalSize = totalSize;
        this.slices = Math.max(1, slices);
        this.remaining = totalSize;
    }

    @Override
    public void step(StrategyContext ctx) {
        if (isDone()) {
            return;
        }
        boolean last = sliceIndex >= slices - 1;
        double child = last ? remaining : Math.min(remaining, Math.max(0, plannedChild(ctx)));
        if (child > 0) {
            ctx.takeMarket(buy, child);
            remaining -= child;
        }
        sliceIndex++;
    }

    @Override
    public boolean isDone() {
        return remaining <= 1e-9 || sliceIndex >= slices;
    }

    /** Planned child size for the current slice (before the final-slice top-up). */
    protected abstract double plannedChild(StrategyContext ctx);
}
