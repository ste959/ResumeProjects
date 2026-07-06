package com.bonddesk.oms.strategy;

import com.bonddesk.oms.market.LiveOrderBook;

import java.time.Instant;

/** The handle a strategy uses each tick to read the market and act on it. */
public final class StrategyContext {

    private final MarketState state;
    private final LiveOrderBook liveBook;
    private final StrategyRun run;
    private final Instant now;

    public StrategyContext(MarketState state, LiveOrderBook liveBook, StrategyRun run, Instant now) {
        this.state = state;
        this.liveBook = liveBook;
        this.run = run;
        this.now = now;
    }

    public MarketState state() {
        return state;
    }

    public double position() {
        return run.book().position();
    }

    /** Take liquidity now: sweep the live book and book the fills (taker). */
    public void takeMarket(boolean buy, double size) {
        if (size <= 0) {
            return;
        }
        ExecutionModel.Sweep sweep = ExecutionModel.sweep(liveBook, buy, size);
        for (double[] hit : sweep.levelsHit()) {
            run.book().apply(Fill.taker(now, buy, hit[0], hit[1]));
        }
        run.recordExecuted(sweep.filledSize(), sweep.notional());
    }

    /** Post/replace two-sided resting quotes for this tick (maker). */
    public void setQuotes(double bid, double ask, double size) {
        run.setQuotes(bid, ask, size);
    }
}
