package com.bonddesk.oms.strategy;

/** Time-Weighted Average Price: split the parent evenly across every slice. */
public final class TwapExecution extends ExecutionStrategy {

    public TwapExecution(boolean buy, double totalSize, int slices) {
        super(buy, totalSize, slices);
    }

    @Override
    public String type() {
        return "TWAP";
    }

    @Override
    protected double plannedChild(StrategyContext ctx) {
        return totalSize / slices;
    }
}
