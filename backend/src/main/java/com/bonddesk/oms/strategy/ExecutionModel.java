package com.bonddesk.oms.strategy;

import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.LiveOrderBook.Level;

import java.util.ArrayList;
import java.util.List;

/**
 * Taker fill model: sweep a marketable order through the live book level-by-level,
 * paying real multi-level slippage. Shared by every execution algorithm.
 */
public final class ExecutionModel {

    /** @param levelsHit list of [price, size] executed against, best-first. */
    public record Sweep(double filledSize, double notional, double vwap, List<double[]> levelsHit) {
        public boolean isEmpty() {
            return filledSize <= 0;
        }
    }

    private ExecutionModel() {
    }

    /** Sweep {@code size} of a market order against the opposite side of {@code book}. */
    public static Sweep sweep(LiveOrderBook book, boolean buy, double size) {
        List<Level> levels = book.snapshot(!buy); // buyers lift asks, sellers hit bids
        double remaining = size;
        double filled = 0;
        double notional = 0;
        List<double[]> hits = new ArrayList<>();
        for (Level level : levels) {
            if (remaining <= 1e-12) break;
            double price = level.price().doubleValue();
            double avail = level.size().doubleValue();
            double take = Math.min(remaining, avail);
            hits.add(new double[]{price, take});
            notional += price * take;
            filled += take;
            remaining -= take;
        }
        double vwap = filled > 0 ? notional / filled : 0.0;
        return new Sweep(filled, notional, vwap, hits);
    }
}
