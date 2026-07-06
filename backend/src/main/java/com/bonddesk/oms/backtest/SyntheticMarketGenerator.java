package com.bonddesk.oms.backtest;

import com.bonddesk.oms.backtest.dto.BacktestDtos.SyntheticRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.SyntheticResult;
import com.bonddesk.oms.exception.BadRequestException;
import com.bonddesk.oms.market.CoinbaseProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Random;

/**
 * Generates a synthetic market — a replayable L2 session produced from a model rather than
 * recorded — with a <em>known</em> planted signal. The book imbalance is skewed toward the next
 * mid move with a configurable strength ({@code imbalanceAlpha}), so a model or strategy can be
 * validated against ground truth: on real data you cannot tell luck from skill; on simulated data
 * with a known signal, you can. Set alpha to 0 for a pure-noise session (a false-positive check).
 *
 * <p>Output uses the same CSV format as the live L2 capture, so it flows through the identical
 * replay/backtest path — the synthetic market is a first-class session.
 */
@Service
public class SyntheticMarketGenerator {

    private static final Logger log = LoggerFactory.getLogger(SyntheticMarketGenerator.class);
    private static final String HEADER = "seq,ts,product,kind,side,price,size";
    private static final String PRODUCT = "SYNTH-USD";
    private static final Instant BASE = Instant.parse("2020-01-01T00:00:00Z");

    private final CoinbaseProperties props;

    public SyntheticMarketGenerator(CoinbaseProperties props) {
        this.props = props;
    }

    public SyntheticResult generate(SyntheticRequest r) {
        if (r.label() == null || r.label().isBlank() || !r.label().matches("[A-Za-z0-9_-]+")) {
            throw new BadRequestException("label is required and must be alphanumeric (A-Z, 0-9, _, -)");
        }
        int durationSec = orDefault(r.durationSeconds(), 300);
        long tickMs = orDefault(r.tickMs(), 250L);
        double midStart = orDefault(r.midStart(), 100.0);
        double volBps = orDefault(r.volBps(), 5.0);
        double driftPerMin = orDefault(r.driftBpsPerMin(), 0.0);
        double spreadBps = orDefault(r.spreadBps(), 4.0);
        int depth = orDefault(r.depthLevels(), 10);
        double levelSize = orDefault(r.levelSize(), 5.0);
        int tradesPerTick = orDefault(r.tradesPerTick(), 1);
        double alpha = orDefault(r.imbalanceAlpha(), 0.0);
        long seed = orDefault(r.seed(), 42L);

        int ticks = Math.max(2, (int) (durationSec * 1000L / tickMs));
        Random rng = new Random(seed);

        // Pre-generate the mid path so the imbalance can be skewed toward the *next* move.
        double[] mid = new double[ticks + 1];
        mid[0] = midStart;
        double driftPerTick = driftPerMin / 10_000.0 * (tickMs / 60_000.0);
        double volPerTick = volBps / 10_000.0;
        for (int i = 1; i <= ticks; i++) {
            mid[i] = mid[i - 1] * (1 + driftPerTick + volPerTick * rng.nextGaussian());
        }

        Path dir = Path.of(props.getL2CaptureDir());
        Path file = dir.resolve("l2-" + r.label() + ".csv");
        long seq = 0;
        long events = 0;
        double priceTick = midStart * 0.0001; // 1 bp price grid for depth levels

        try {
            Files.createDirectories(dir);
            try (BufferedWriter w = Files.newBufferedWriter(file)) {
                w.write(HEADER);
                w.write('\n');
                for (int t = 0; t < ticks; t++) {
                    Instant ts = BASE.plusMillis(t * tickMs);
                    double m = mid[t];
                    double nextRet = (mid[t + 1] - m) / m;
                    // Skew the book toward the next move (the planted signal, strength alpha),
                    // plus idiosyncratic noise so imbalance varies even with no signal — a proper
                    // false-positive check (alpha = 0 → imbalance varies but is uncorrelated).
                    double skew = Math.tanh(alpha * nextRet / volPerTick + 0.6 * rng.nextGaussian());
                    skew = Math.max(-0.9, Math.min(0.9, skew));
                    double halfSpread = m * spreadBps / 10_000.0 / 2.0;

                    long snapSeq = ++seq;
                    for (int i = 0; i < depth; i++) {
                        double decay = Math.exp(-0.2 * i);
                        double bidPx = m - halfSpread - i * priceTick;
                        double askPx = m + halfSpread + i * priceTick;
                        events += writeRow(w, snapSeq, ts, "SNAP", "B", bidPx, levelSize * decay * (1 + skew));
                        events += writeRow(w, snapSeq, ts, "SNAP", "A", askPx, levelSize * decay * (1 - skew));
                    }
                    for (int k = 0; k < tradesPerTick; k++) {
                        boolean buyAggressor = rng.nextDouble() < 0.5 + skew / 2.0; // flow leans with the skew
                        double px = buyAggressor ? m + halfSpread : m - halfSpread;
                        events += writeRow(w, ++seq, ts, "TRD", buyAggressor ? "B" : "A", px,
                                levelSize * 0.2 * (0.5 + rng.nextDouble()));
                    }
                }
            }
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }

        log.info("Generated synthetic session '{}' ({} ticks, {} events, alpha={})",
                r.label(), ticks, events, alpha);
        return new SyntheticResult(r.label(), PRODUCT, file.toString(), events, ticks, alpha);
    }

    private static int writeRow(BufferedWriter w, long seq, Instant ts, String kind, String side,
                                double price, double size) throws IOException {
        w.write(seq + "," + ts + "," + PRODUCT + "," + kind + "," + side + ","
                + round(price) + "," + round(size));
        w.write('\n');
        return 1;
    }

    private static String round(double v) {
        return java.math.BigDecimal.valueOf(Math.round(v * 1e8) / 1e8).toPlainString();
    }

    private static int orDefault(Integer v, int def) {
        return v == null ? def : v;
    }

    private static long orDefault(Long v, long def) {
        return v == null ? def : v;
    }

    private static double orDefault(Double v, double def) {
        return v == null ? def : v;
    }
}
