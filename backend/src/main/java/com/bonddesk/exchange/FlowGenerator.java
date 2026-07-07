package com.bonddesk.exchange;

import java.util.Random;

/**
 * An agent-based order-flow simulator that keeps the market alive around a fair price:
 * <ul>
 *   <li><b>Noise makers</b> — passive limit orders sprinkled near the fair, providing baseline
 *       resting liquidity besides the market maker (and cancelling out over time).</li>
 *   <li><b>Noise takers</b> — random-direction market orders (uninformed flow the maker profits from).</li>
 *   <li><b>Informed takers</b> — market orders in the direction of the <i>next</i> price move; when
 *       they lift the maker's stale quote they impose <b>adverse selection</b>, exactly the effect a
 *       real market maker must price. Their share is <code>informedFraction</code>.</li>
 * </ul>
 * Deterministic given its seed. Not thread-safe; driven on the engine thread.
 */
public final class FlowGenerator {

    private final Random rng;
    private final long quoteRange;          // ticks around fair for noise makers
    private final double informedFraction;  // share of takers that are informed
    private final long[] recent = new long[256];
    private int ring;

    public FlowGenerator(long seed, long quoteRange, double informedFraction) {
        this.rng = new Random(seed);
        this.quoteRange = quoteRange;
        this.informedFraction = informedFraction;
    }

    /**
     * Submit one step of flow. {@code signal} is the anticipated fair move (informed takers trade its
     * sign); {@code intensity} orders are generated. Should be called <i>before</i> the maker requotes
     * so informed flow hits the stale quote.
     */
    public void step(OrderBook book, long fairTicks, double signal, int intensity) {
        for (int i = 0; i < intensity; i++) {
            double u = rng.nextDouble();
            if (u < 0.45) {
                // noise maker — passive liquidity a few ticks off the fair
                Side side = rng.nextBoolean() ? Side.BUY : Side.SELL;
                long off = 1 + rng.nextInt((int) quoteRange);
                long px = side == Side.BUY ? fairTicks - off : fairTicks + off;
                SubmitResult r = book.submit("noise" + rng.nextInt(24), side, OrderType.LIMIT,
                        TimeInForce.GTC, false, px, 1 + rng.nextInt(3));
                if (r.status() == SubmitResult.Status.RESTING) {
                    recent[ring] = r.orderId();
                    ring = (ring + 1) & 255;
                }
            } else if (u < 0.65) {
                // cancel an older resting noise order — keeps the book from growing without bound
                int idx = rng.nextInt(256);
                if (recent[idx] != 0) {
                    book.cancel(recent[idx]);
                    recent[idx] = 0;
                }
            } else {
                // taker — informed (toward the move) or noise (random)
                Side side;
                if (rng.nextDouble() < informedFraction && Math.abs(signal) > 1e-9) {
                    side = signal > 0 ? Side.BUY : Side.SELL;
                } else {
                    side = rng.nextBoolean() ? Side.BUY : Side.SELL;
                }
                book.submit("taker" + rng.nextInt(24), side, OrderType.MARKET, TimeInForce.IOC,
                        false, 0, 1 + rng.nextInt(4));
            }
        }
    }
}
