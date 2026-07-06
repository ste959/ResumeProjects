package com.bonddesk.oms.strategy;

/**
 * A trading strategy stepped once per engine tick. Execution algorithms *take* liquidity
 * (via {@link StrategyContext#takeMarket}) and finish; a market maker *makes* liquidity
 * (via {@link StrategyContext#setQuotes}) and runs until stopped.
 */
public interface Strategy {

    String type();

    /** React to the latest market state — place child orders and/or update quotes. */
    void step(StrategyContext ctx);

    /** True once the strategy has nothing left to do (e.g. a parent order is filled). */
    default boolean isDone() {
        return false;
    }
}
