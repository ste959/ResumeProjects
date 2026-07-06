package com.bonddesk.oms.strategy;

/**
 * A per-tick snapshot of the market handed to a strategy: top of book, fair-value
 * estimates, a rolling volatility estimate (of mid log-returns) and recent traded
 * volume. All doubles — the strategy math is numeric and this is a paper engine.
 */
public record MarketState(
        String product,
        double bestBid,
        double bestAsk,
        double mid,
        double microprice,
        double sigma,          // per-tick volatility of mid returns
        double recentVolume    // traded size since the last tick
) {
    public double spread() {
        return bestAsk - bestBid;
    }
}
