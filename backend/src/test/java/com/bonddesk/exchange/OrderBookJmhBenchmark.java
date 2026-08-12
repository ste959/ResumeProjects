package com.bonddesk.exchange;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OperationsPerInvocation;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;
import org.openjdk.jmh.runner.Runner;
import org.openjdk.jmh.runner.RunnerException;
import org.openjdk.jmh.runner.options.OptionsBuilder;

import java.util.Random;
import java.util.concurrent.TimeUnit;

/**
 * Rigorous JMH harness for the matching engine — the forked-JVM, dead-code-protected counterpart to
 * {@link ExchangeBenchmarkTest}. JMH handles what a hand-rolled loop can't: a separate forked JVM,
 * managed warm-up/measurement iterations, and {@link Blackhole} consumption so the JIT can't elide
 * the work. Two modes are exposed — sustained throughput and per-op sample latency — over an
 * identical pre-generated flow.
 *
 * <p>Not a unit test (no JUnit annotations), so Surefire ignores it. Run it explicitly:
 * <pre>
 *   ./mvnw -q test-compile
 *   java -cp "target/test-classes:target/classes:$(./mvnw -q dependency:build-classpath -Dmdep.outputFile=/dev/stdout)" \
 *        com.bonddesk.exchange.OrderBookJmhBenchmark          # add -prof gc for allocation/op
 * </pre>
 */
@State(Scope.Thread)
@Fork(1)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class OrderBookJmhBenchmark {

    private static final int BATCH = 100_000;

    private byte[] op;
    private boolean[] buy;
    private long[] price;
    private long[] qty;
    private String[] who;

    @Setup(Level.Trial)
    public void generate() {
        String[] makers = new String[16];
        for (int k = 0; k < 16; k++) makers[k] = "mm" + k;
        String[] takers = new String[8];
        for (int k = 0; k < 8; k++) takers[k] = "taker" + k;

        op = new byte[BATCH];
        buy = new boolean[BATCH];
        price = new long[BATCH];
        qty = new long[BATCH];
        who = new String[BATCH];

        Random rng = new Random(42);
        long mid = 50_000;
        for (int i = 0; i < BATCH; i++) {
            mid += rng.nextInt(3) - 1;
            double u = rng.nextDouble();
            boolean side = rng.nextBoolean();
            buy[i] = side;
            if (u < 0.20) {
                op[i] = 0; price[i] = 0; qty[i] = 1 + rng.nextInt(5); who[i] = takers[i & 7];
            } else if (u < 0.55) {
                op[i] = 1;
            } else {
                op[i] = 2;
                price[i] = side ? mid - 1 - rng.nextInt(5) : mid + 1 + rng.nextInt(5);
                qty[i] = 1 + rng.nextInt(9);
                who[i] = makers[i & 15];
            }
        }
    }

    private void replay(Blackhole bh) {
        OrderBook book = new OrderBook("BTC-USD");
        long[] restingIds = new long[4096];
        int ring = 0;
        for (int i = 0; i < BATCH; i++) {
            switch (op[i]) {
                case 0 -> bh.consume(book.submit(who[i], buy[i] ? Side.BUY : Side.SELL,
                        OrderType.MARKET, TimeInForce.IOC, false, 0, qty[i]));
                case 1 -> {
                    if (restingIds[ring] != 0) { bh.consume(book.cancel(restingIds[ring])); restingIds[ring] = 0; }
                }
                default -> {
                    SubmitResult r = book.submit(who[i], buy[i] ? Side.BUY : Side.SELL,
                            OrderType.LIMIT, TimeInForce.GTC, false, price[i], qty[i]);
                    if (r.status() == SubmitResult.Status.RESTING) restingIds[ring] = r.orderId();
                    bh.consume(r);
                }
            }
            ring = (ring + 1) & 4095;
        }
        bh.consume(book.tradeCount());
    }

    @Benchmark
    @BenchmarkMode(Mode.Throughput)
    @OperationsPerInvocation(BATCH)
    public void throughput(Blackhole bh) {
        replay(bh);
    }

    @Benchmark
    @BenchmarkMode(Mode.SampleTime)
    @OperationsPerInvocation(BATCH)
    public void sampleLatency(Blackhole bh) {
        replay(bh);
    }

    public static void main(String[] args) throws RunnerException {
        new Runner(new OptionsBuilder()
                .include(OrderBookJmhBenchmark.class.getSimpleName())
                .build()).run();
    }
}
