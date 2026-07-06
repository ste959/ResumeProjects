package com.bonddesk.oms.market;

import com.bonddesk.oms.market.LiveOrderBook.Level;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import jakarta.annotation.PreDestroy;
import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Captures the full-depth L2 event stream (order-book snapshots + incremental updates +
 * trade prints) to a replayable CSV log, which the backtester replays to reconstruct the
 * book tick-by-tick. Unlike {@link MarketRecorder} (a 1 Hz top-of-book sample), this is a
 * complete event log — the fidelity a realistic fill simulation needs.
 *
 * <p>Capture must never backpressure the live feed: the feed thread only formats a line
 * and enqueues it (a lock-free {@link ConcurrentLinkedQueue}); a scheduled drain does the
 * file I/O. The {@code ts} column is the local <em>receipt</em> time — deliberately
 * distinct from exchange time, a distinction that matters for latency modelling.
 */
@Component
@ConditionalOnProperty(prefix = "oms.crypto", name = "l2-capture-enabled", havingValue = "true", matchIfMissing = true)
public class L2Recorder {

    private static final Logger log = LoggerFactory.getLogger(L2Recorder.class);
    private static final String HEADER = "seq,ts,product,kind,side,price,size";

    private final CoinbaseProperties props;
    private final Clock clock;
    private final AtomicLong seq = new AtomicLong();
    private final Queue<String> queue = new ConcurrentLinkedQueue<>();

    private BufferedWriter writer;
    private LocalDate openFor;

    public L2Recorder(CoinbaseProperties props, Clock clock) {
        this.props = props;
        this.clock = clock;
    }

    /** Full order-book snapshot — all levels share one sequence so replay can group them. */
    public void snapshot(String product, List<Level> bids, List<Level> asks) {
        long s = seq.incrementAndGet();
        String ts = clock.instant().toString();
        for (Level l : bids) {
            queue.add(row(s, ts, product, "SNAP", "B", l.price(), l.size()));
        }
        for (Level l : asks) {
            queue.add(row(s, ts, product, "SNAP", "A", l.price(), l.size()));
        }
    }

    /** One incremental level update (size 0 = level removed). */
    public void update(String product, boolean bid, BigDecimal price, BigDecimal size) {
        queue.add(row(seq.incrementAndGet(), clock.instant().toString(), product, "UPD",
                bid ? "B" : "A", price, size));
    }

    /** A trade print; {@code side} is the aggressor side (buy → B, sell → A). */
    public void trade(String product, BigDecimal price, BigDecimal size, String side) {
        String s = side != null && side.toLowerCase().startsWith("s") ? "A" : "B";
        queue.add(row(seq.incrementAndGet(), clock.instant().toString(), product, "TRD", s, price, size));
    }

    private static String row(long seq, String ts, String product, String kind, String side,
                              BigDecimal price, BigDecimal size) {
        return seq + "," + ts + "," + product + "," + kind + "," + side + ","
                + price.toPlainString() + "," + size.toPlainString();
    }

    /** Drain the queue to disk. Runs on a scheduler thread, off the feed's hot path. */
    @Scheduled(fixedDelay = 1000)
    public synchronized void flush() {
        if (queue.isEmpty()) {
            return;
        }
        try {
            rollFileIfNeeded();
            String line;
            while ((line = queue.poll()) != null) {
                writer.write(line);
                writer.write('\n');
            }
            writer.flush();
        } catch (IOException e) {
            log.debug("L2 capture flush failed: {}", e.getMessage());
        }
    }

    private void rollFileIfNeeded() throws IOException {
        LocalDate today = LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC);
        if (writer != null && today.equals(openFor)) {
            return;
        }
        if (writer != null) {
            writer.close();
        }
        Path dir = Path.of(props.getL2CaptureDir());
        Files.createDirectories(dir);
        Path file = dir.resolve("l2-" + today + ".csv");
        boolean fresh = !Files.exists(file);
        writer = Files.newBufferedWriter(file, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        if (fresh) {
            writer.write(HEADER);
            writer.write('\n');
        }
        openFor = today;
    }

    @PreDestroy
    public synchronized void close() {
        flush();
        if (writer != null) {
            try {
                writer.close();
            } catch (IOException e) {
                log.debug("L2 capture close failed: {}", e.getMessage());
            }
        }
    }
}
