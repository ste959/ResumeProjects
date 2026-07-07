package com.bonddesk.exchange;

import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Random;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * A throughput + latency benchmark for the matching engine — the metric an HFT/market-making firm
 * actually cares about. Drives a realistic bounded flow (limit adds around a random-walking mid,
 * marketable takers, and cancels) through a single book and reports orders/sec and per-submit
 * latency percentiles. Asserts only a very loose floor (so it never flakes on CI hardware); the
 * printed numbers are the point.
 */
class ExchangeBenchmarkTest {

    @Test
    void throughputAndLatency() {
        final int warmup = 100_000;
        final int measured = 400_000;
        run(new OrderBook("BTC-USD"), warmup, null);        // JIT warm-up

        long[] latencies = new long[measured];
        OrderBook book = new OrderBook("BTC-USD");
        long start = System.nanoTime();
        long trades = run(book, measured, latencies);
        long elapsed = System.nanoTime() - start;

        double perSec = measured / (elapsed / 1e9);
        Arrays.sort(latencies);
        long p50 = latencies[(int) (measured * 0.50)];
        long p99 = latencies[(int) (measured * 0.99)];
        long p999 = latencies[(int) (measured * 0.999)];

        System.out.printf("%n=== Matching engine benchmark ===%n");
        System.out.printf("  orders submitted : %,d%n", measured);
        System.out.printf("  throughput       : %,.0f orders/sec%n", perSec);
        System.out.printf("  latency  p50/p99/p99.9 : %d / %d / %d ns%n", p50, p99, p999);
        System.out.printf("  trades matched   : %,d%n", trades);
        System.out.printf("  resting at end   : %,d lots%n%n", book.restingQuantity());

        assertThat(perSec).isGreaterThan(100_000.0);        // loose floor; real numbers are far higher
        assertThat(p99).isLessThan(50_000L);                // p99 under 50µs
    }

    /** A bounded, realistic order flow. Returns the number of trades matched. */
    private long run(OrderBook book, int n, long[] latencies) {
        Random rng = new Random(42);
        long mid = 50_000;                 // starting mid in ticks
        long[] restingIds = new long[4096];
        int ring = 0;

        for (int i = 0; i < n; i++) {
            mid += rng.nextInt(3) - 1;      // ±1 tick random walk
            double u = rng.nextDouble();
            long t0 = latencies != null ? System.nanoTime() : 0;

            if (u < 0.20) {
                // marketable taker — crosses the spread and matches resting liquidity
                Side side = rng.nextBoolean() ? Side.BUY : Side.SELL;
                book.submit("taker" + (i & 7), side, OrderType.MARKET, TimeInForce.IOC, false, 0, 1 + rng.nextInt(5));
            } else if (u < 0.55 && restingIds[ring] != 0) {
                book.cancel(restingIds[ring]);   // cancel an older resting order (keeps the book bounded)
                restingIds[ring] = 0;
            } else {
                // passive maker a few ticks off the mid
                Side side = rng.nextBoolean() ? Side.BUY : Side.SELL;
                long px = side == Side.BUY ? mid - 1 - rng.nextInt(5) : mid + 1 + rng.nextInt(5);
                SubmitResult r = book.submit("mm" + (i & 15), side, OrderType.LIMIT, TimeInForce.GTC, false, px, 1 + rng.nextInt(9));
                if (r.status() == SubmitResult.Status.RESTING) {
                    restingIds[ring] = r.orderId();
                }
            }
            if (latencies != null) {
                latencies[i] = System.nanoTime() - t0;
                ring = (ring + 1) & 4095;
            } else {
                ring = (ring + 1) & 4095;
            }
        }
        return book.tradeCount();
    }
}
