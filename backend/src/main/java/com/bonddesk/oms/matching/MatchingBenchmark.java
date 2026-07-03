package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;

import java.util.Arrays;
import java.util.List;
import java.util.Random;

/**
 * Standalone throughput + latency benchmark for the pure {@link OrderBook} — no Spring,
 * no database, no I/O, single thread. Reports orders/sec and per-submit latency
 * percentiles for a realistic churning flow of limit and market orders.
 *
 * <p>Run: {@code java -cp target/classes com.bonddesk.oms.matching.MatchingBenchmark [count]}.
 * Measures the hot path only; persistence and event publishing (the OMS integration)
 * are intentionally out of scope here.
 */
public final class MatchingBenchmark {

    public static void main(String[] args) {
        int measured = args.length > 0 ? Integer.parseInt(args[0]) : 2_000_000;
        int warmup = Math.min(measured / 5, 300_000);

        // Pre-generate the flow into primitive arrays so generation cost is out of the timed loop.
        int total = warmup + measured;
        Random rng = new Random(42);
        OrderSide[] sides = new OrderSide[total];
        OrderType[] types = new OrderType[total];
        long[] prices = new long[total];
        long[] qtys = new long[total];
        for (int i = 0; i < total; i++) {
            sides[i] = rng.nextBoolean() ? OrderSide.BUY : OrderSide.SELL;
            types[i] = rng.nextInt(100) < 20 ? OrderType.MARKET : OrderType.LIMIT;
            prices[i] = 999_500 + rng.nextInt(1_001); // tight band 99.95–100.05 so the book churns
            qtys[i] = 1 + rng.nextInt(100);
        }

        OrderBook book = new OrderBook("BENCH");
        long id = 0;

        // Warmup — let the JIT compile the hot path.
        for (int i = 0; i < warmup; i++) {
            book.submit(new BookOrder(++id, sides[i], types[i], prices[i], qtys[i], null));
        }

        long[] latencies = new long[measured];
        long trades = 0;
        long start = System.nanoTime();
        for (int i = 0; i < measured; i++) {
            int k = warmup + i;
            BookOrder o = new BookOrder(++id, sides[k], types[k], prices[k], qtys[k], null);
            long t0 = System.nanoTime();
            List<Trade> result = book.submit(o);
            latencies[i] = System.nanoTime() - t0;
            trades += result.size();
        }
        long elapsedNs = System.nanoTime() - start;

        Arrays.sort(latencies);
        double seconds = elapsedNs / 1e9;
        System.out.println("=== OrderBook benchmark ===");
        System.out.printf("orders submitted : %,d%n", measured);
        System.out.printf("trades generated : %,d%n", trades);
        System.out.printf("elapsed          : %.3f s%n", seconds);
        System.out.printf("throughput       : %,.0f orders/sec%n", measured / seconds);
        System.out.printf("latency p50       : %,d ns%n", latencies[(int) (measured * 0.50)]);
        System.out.printf("latency p90       : %,d ns%n", latencies[(int) (measured * 0.90)]);
        System.out.printf("latency p99       : %,d ns%n", latencies[(int) (measured * 0.99)]);
        System.out.printf("latency p99.9     : %,d ns%n", latencies[(int) (measured * 0.999)]);
        System.out.printf("resting orders    : %,d (book depth left)%n", book.restingQuantity());
    }

    private MatchingBenchmark() {
    }
}
