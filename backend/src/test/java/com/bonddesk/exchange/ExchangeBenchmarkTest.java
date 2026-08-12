package com.bonddesk.exchange;

import com.sun.management.ThreadMXBean;
import org.junit.jupiter.api.Test;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.Random;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Throughput + latency + allocation benchmark for the matching engine — the metrics an HFT/market-
 * making desk actually cares about. It drives a realistic bounded flow (limit adds around a
 * random-walking mid, marketable takers, cancels) through a single book.
 *
 * <p>Methodology (so the numbers mean something):
 * <ul>
 *   <li><b>The whole flow is pre-generated into primitive arrays</b> before timing — order type,
 *       side, price, quantity and the interned participant id — so the timed region is pure engine
 *       work, not {@code Random} draws or {@code "mm"+i} string building a real feed handler wouldn't do.</li>
 *   <li><b>Throughput and latency are separate passes.</b> The throughput pass takes no per-op
 *       timestamp (two {@code nanoTime()} calls per op would tax the very thing being measured); a
 *       second pass records per-submit latency for the percentiles.</li>
 *   <li><b>Warm-up runs the identical flow through an identical book</b> so the measured pass isn't
 *       paying first-touch HashMap/TreeMap growth or cold JIT.</li>
 *   <li><b>Allocation is measured</b> with {@code ThreadMXBean.getThreadAllocatedBytes} around the
 *       timed region — a self-contained stand-in for {@code jmh -prof gc}, and the evidence behind the
 *       "allocation-light hot path" claim.</li>
 * </ul>
 * This is a hand-rolled in-JVM benchmark (single thread, in-memory), asserting only loose floors so it
 * never flakes on CI hardware — the printed numbers are the point. For rigorous measurement (forked
 * JVM, dead-code elimination via Blackhole) a JMH harness is the next step; the pre-generation and
 * separate-pass discipline here mirror what JMH would enforce.
 */
class ExchangeBenchmarkTest {

    /** A pre-generated flow: everything the timed loop needs, computed up front. */
    private static final class Flow {
        final byte[] op;         // 0 = marketable taker, 1 = cancel, 2 = passive maker
        final boolean[] buy;
        final long[] price;      // 0 for takers (MARKET)
        final long[] qty;
        final String[] who;      // interned participant id (no allocation in the timed loop)
        Flow(int n) { op = new byte[n]; buy = new boolean[n]; price = new long[n]; qty = new long[n]; who = new String[n]; }
        int size() { return op.length; }
    }

    private static Flow generate(int n) {
        // Interned participant ids, built once (a real engine keys off ints/handles, not fresh strings).
        String[] makers = new String[16];
        for (int k = 0; k < 16; k++) makers[k] = "mm" + k;
        String[] takers = new String[8];
        for (int k = 0; k < 8; k++) takers[k] = "taker" + k;

        Flow f = new Flow(n);
        Random rng = new Random(42);
        long mid = 50_000;
        for (int i = 0; i < n; i++) {
            mid += rng.nextInt(3) - 1;                 // ±1 tick random walk
            double u = rng.nextDouble();
            boolean side = rng.nextBoolean();
            f.buy[i] = side;
            if (u < 0.20) {                            // marketable taker
                f.op[i] = 0;
                f.price[i] = 0;
                f.qty[i] = 1 + rng.nextInt(5);
                f.who[i] = takers[i & 7];
            } else if (u < 0.55) {                     // cancel a recently-rested order
                f.op[i] = 1;
            } else {                                   // passive maker a few ticks off the mid
                f.op[i] = 2;
                f.price[i] = side ? mid - 1 - rng.nextInt(5) : mid + 1 + rng.nextInt(5);
                f.qty[i] = 1 + rng.nextInt(9);
                f.who[i] = makers[i & 15];
            }
        }
        return f;
    }

    /** Replay the pre-generated flow. When {@code latencies != null}, record per-submit nanos. */
    private static long run(OrderBook book, Flow f, long[] latencies) {
        long[] restingIds = new long[4096];
        int ring = 0;
        for (int i = 0, n = f.size(); i < n; i++) {
            long t0 = latencies != null ? System.nanoTime() : 0;
            switch (f.op[i]) {
                case 0 -> book.submit(f.who[i], f.buy[i] ? Side.BUY : Side.SELL,
                        OrderType.MARKET, TimeInForce.IOC, false, 0, f.qty[i]);
                case 1 -> {
                    if (restingIds[ring] != 0) { book.cancel(restingIds[ring]); restingIds[ring] = 0; }
                }
                default -> {
                    SubmitResult r = book.submit(f.who[i], f.buy[i] ? Side.BUY : Side.SELL,
                            OrderType.LIMIT, TimeInForce.GTC, false, f.price[i], f.qty[i]);
                    if (r.status() == SubmitResult.Status.RESTING) restingIds[ring] = r.orderId();
                }
            }
            if (latencies != null) latencies[i] = System.nanoTime() - t0;
            ring = (ring + 1) & 4095;
        }
        return book.tradeCount();
    }

    @Test
    void throughputLatencyAndAllocation() {
        final int measured = 400_000;
        Flow flow = generate(measured);
        ThreadMXBean threads = (ThreadMXBean) ManagementFactory.getThreadMXBean();

        run(new OrderBook("BTC-USD"), flow, null);            // JIT + structure warm-up on the same flow

        // --- Pass 1: throughput + allocation (no per-op instrumentation in the timed region) ---
        OrderBook book = new OrderBook("BTC-USD");
        long tid = Thread.currentThread().threadId();
        long allocBefore = threads.getThreadAllocatedBytes(tid);
        long start = System.nanoTime();
        long trades = run(book, flow, null);
        long elapsed = System.nanoTime() - start;
        long allocated = threads.getThreadAllocatedBytes(tid) - allocBefore;
        double perSec = measured / (elapsed / 1e9);

        // --- Pass 2: latency percentiles (separate run so timers don't tax throughput) ---
        long[] latencies = new long[measured];
        run(new OrderBook("BTC-USD"), flow, latencies);
        Arrays.sort(latencies);

        System.out.printf("%n=== Matching engine benchmark (single thread, in-memory) ===%n");
        System.out.printf("  orders submitted : %,d%n", measured);
        System.out.printf("  throughput       : %,.0f orders/sec%n", perSec);
        System.out.printf("  latency p50/p99/p99.9 : %d / %d / %d ns%n",
                latencies[(int) (measured * 0.50)], latencies[(int) (measured * 0.99)], latencies[(int) (measured * 0.999)]);
        System.out.printf("  allocation       : %,.1f bytes/order%n", allocated / (double) measured);
        System.out.printf("  trades matched   : %,d  |  resting at end : %,d lots%n%n", trades, book.restingQuantity());

        assertThat(perSec).isGreaterThan(100_000.0);          // loose floor; real numbers are far higher
        assertThat(latencies[(int) (measured * 0.99)]).isLessThan(50_000L); // p99 under 50µs
    }
}
