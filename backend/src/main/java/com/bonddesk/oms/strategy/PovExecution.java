package com.bonddesk.oms.strategy;

/**
 * Percentage-Of-Volume: each slice trades a fixed fraction of the volume the market has
 * traded since the last tick, so the algo speeds up when the market is active and slows
 * when it is quiet. Capped by the slice budget so it still completes.
 */
public final class PovExecution extends ExecutionStrategy {

    // Volatile so a live "modify participation" from an HTTP thread is visible to the runner thread
    // that reads it each tick (see StrategyService.modify).
    private volatile double participation;

    public PovExecution(boolean buy, double totalSize, int slices, double participation) {
        super(buy, totalSize, slices);
        this.participation = participation;
    }

    /** Adjust the volume-participation rate on a running POV algo. */
    public void setParticipation(double participation) {
        this.participation = participation;
    }

    public double participation() {
        return participation;
    }

    @Override
    public String type() {
        return "POV";
    }

    @Override
    protected double plannedChild(StrategyContext ctx) {
        return participation * ctx.state().recentVolume();
    }
}
