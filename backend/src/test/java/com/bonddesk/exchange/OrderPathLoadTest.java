package com.bonddesk.exchange;

import java.util.Arrays;
import java.util.Random;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Concurrent load / soak test for the matching path — the end-to-end-under-load counterpart to the
 * single-thread {@link ExchangeBenchmarkTest} microbenchmark.
 *
 * <p>It mirrors the engine's real concurrency model: many order books (instruments), each a
 * single-writer core guarded by its own lock (as {@link com.bonddesk.oms.matching.MatchingService}
 * does with {@code synchronized(book)}). It then drives sustained, saturating load from many client
 * threads across those books and reports, at each thread count, the achieved <b>throughput</b> and the
 * <b>tail-latency</b> percentiles under contention — the numbers that a microbench can't show.
 *
 * <p>Methodology: the order flow is pre-generated per thread (so the timed loop is pure submit work,
 * not RNG/allocation), a warm-up pass JITs the code, per-op latency is recorded in a per-thread ring
 * buffer (bounded memory, steady-state samples), and throughput is wall-clock ops/sec. Not a networked
 * load test — it isolates the matching core; the full persistence path is DB-bound (see docs/follow-ups).
 *
 * <p>Run:  {@code java -cp backend/target/test-classes:backend/target/classes
 * com.bonddesk.exchange.OrderPathLoadTest [durationMillis] [instruments] [maxThreads]}
 */
public final class OrderPathLoadTest {

    private static final long SAMPLE_BUDGET = 2_000_000;   // total latency samples kept, split per thread

    /** Pre-generated, read-only order flow. */
    private record Flow(byte[] op, boolean[] buy, long[] price, long[] qty, int[] inst, String[] who) {
        int size() { return op.length; }
    }

    private static Flow generate(int n, int instruments) {
        String[] makers = new String[16];
        for (int k = 0; k < 16; k++) makers[k] = "mm" + k;
        String[] takers = new String[8];
        for (int k = 0; k < 8; k++) takers[k] = "t" + k;

        byte[] op = new byte[n];
        boolean[] buy = new boolean[n];
        long[] price = new long[n];
        long[] qty = new long[n];
        int[] inst = new int[n];
        String[] who = new String[n];
        Random rng = new Random(42);
        long mid = 50_000;
        for (int i = 0; i < n; i++) {
            mid += rng.nextInt(3) - 1;
            inst[i] = rng.nextInt(instruments);
            boolean side = rng.nextBoolean();
            buy[i] = side;
            double u = rng.nextDouble();
            if (u < 0.20) {                                // marketable taker
                op[i] = 0; price[i] = 0; qty[i] = 1 + rng.nextInt(5); who[i] = takers[i & 7];
            } else if (u < 0.55) {                         // cancel-ish (re-submit passive; keeps books bounded)
                op[i] = 2;
                price[i] = side ? mid - 1 - rng.nextInt(5) : mid + 1 + rng.nextInt(5);
                qty[i] = 1 + rng.nextInt(9); who[i] = makers[i & 15];
            } else {                                       // passive maker
                op[i] = 2;
                price[i] = side ? mid - 1 - rng.nextInt(5) : mid + 1 + rng.nextInt(5);
                qty[i] = 1 + rng.nextInt(9); who[i] = makers[i & 15];
            }
        }
        return new Flow(op, buy, price, qty, inst, who);
    }

    private record Result(int threads, double throughputPerSec, long p50, long p99, long p999, long ops) {}

    private static Result run(Flow flow, OrderBook[] books, int threads, long durationMillis) throws InterruptedException {
        int perThreadCap = (int) Math.max(10_000, SAMPLE_BUDGET / threads);
        long[][] latencies = new long[threads][perThreadCap];
        int[] recorded = new int[threads];
        AtomicLong totalOps = new AtomicLong();
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        long deadlineNanos = durationMillis * 1_000_000L;

        Thread[] workers = new Thread[threads];
        for (int t = 0; t < threads; t++) {
            final int tid = t;
            workers[t] = new Thread(() -> {
                long[] lat = latencies[tid];
                int cap = lat.length;
                int idx = tid * 7919;                      // stagger each thread's start offset into the flow
                long ops = 0, ring = 0;
                try { start.await(); } catch (InterruptedException e) { return; }
                long begin = System.nanoTime();
                while (System.nanoTime() - begin < deadlineNanos) {
                    int i = Math.floorMod(idx++, flow.size());
                    OrderBook book = books[flow.inst[i]];
                    long t0 = System.nanoTime();
                    synchronized (book) {                  // one writer per book — the engine's model
                        book.submit(flow.who[i], flow.buy[i] ? Side.BUY : Side.SELL,
                                flow.op[i] == 0 ? OrderType.MARKET : OrderType.LIMIT,
                                flow.op[i] == 0 ? TimeInForce.IOC : TimeInForce.GTC,
                                false, flow.price[i], flow.qty[i]);
                    }
                    lat[(int) (ring++ % cap)] = System.nanoTime() - t0;   // ring buffer: steady-state samples
                    ops++;
                }
                recorded[tid] = (int) Math.min(ring, cap);
                totalOps.addAndGet(ops);
                done.countDown();
            }, "load-" + tid);
            workers[t].start();
        }

        long wallStart = System.nanoTime();
        start.countDown();
        done.await();
        double elapsedSec = (System.nanoTime() - wallStart) / 1e9;

        int total = 0;
        for (int r : recorded) total += r;
        long[] merged = new long[total];
        int off = 0;
        for (int t = 0; t < threads; t++) {
            System.arraycopy(latencies[t], 0, merged, off, recorded[t]);
            off += recorded[t];
        }
        Arrays.sort(merged);
        long ops = totalOps.get();
        return new Result(threads, ops / elapsedSec,
                pct(merged, 0.50), pct(merged, 0.99), pct(merged, 0.999), ops);
    }

    private static long pct(long[] sorted, double q) {
        if (sorted.length == 0) return 0;
        return sorted[Math.min(sorted.length - 1, (int) (sorted.length * q))];
    }

    public static void main(String[] args) throws InterruptedException {
        long durationMillis = args.length > 0 ? Long.parseLong(args[0]) : 2000;
        int instruments = args.length > 1 ? Integer.parseInt(args[1]) : 16;
        int maxThreads = args.length > 2 ? Integer.parseInt(args[2])
                : Math.max(1, Runtime.getRuntime().availableProcessors());

        Flow flow = generate(1_000_000, instruments);

        System.out.printf("%n=== Matching-path load test (%d instruments, %d ms per level) ===%n",
                instruments, durationMillis);
        System.out.printf("  %-8s %16s %12s %12s %12s%n", "threads", "throughput/s", "p50", "p99", "p99.9");

        Result best = null;
        for (int threads = 1; threads <= maxThreads; threads = threads == 1 ? 2 : threads * 2) {
            OrderBook[] books = new OrderBook[instruments];
            for (int b = 0; b < instruments; b++) books[b] = new OrderBook("SYM-" + b);
            run(flow, books, threads, Math.min(500, durationMillis));   // warm-up (JIT)

            OrderBook[] fresh = new OrderBook[instruments];
            for (int b = 0; b < instruments; b++) fresh[b] = new OrderBook("SYM-" + b);
            Result r = run(flow, fresh, threads, durationMillis);
            best = r;
            System.out.printf("  %-8d %,16.0f %10d ns %10d ns %10d ns%n",
                    r.threads(), r.throughputPerSec(), r.p50(), r.p99(), r.p999());
        }

        // Machine-readable result for the validation harness (max-thread run).
        System.out.printf("LAB_RESULT {\"threads\": %d, \"throughput_per_sec\": %.0f, "
                        + "\"p50_ns\": %d, \"p99_ns\": %d, \"p999_ns\": %d, \"orders\": %d}%n",
                best.threads(), best.throughputPerSec(), best.p50(), best.p99(), best.p999(), best.ops());
    }
}
