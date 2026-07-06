package com.bonddesk.oms.backtest;

import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestResult;
import com.bonddesk.oms.backtest.dto.BacktestDtos.FillView;
import com.bonddesk.oms.exception.BadRequestException;
import com.bonddesk.oms.exception.NotFoundException;
import com.bonddesk.oms.market.CoinbaseProperties;
import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.LiveOrderBook.Level;
import com.bonddesk.oms.strategy.AlmgrenChrissExecution;
import com.bonddesk.oms.strategy.MarketState;
import com.bonddesk.oms.strategy.PnlBook;
import com.bonddesk.oms.strategy.PovExecution;
import com.bonddesk.oms.strategy.Strategy;
import com.bonddesk.oms.strategy.StrategyContext;
import com.bonddesk.oms.strategy.StrategyRun;
import com.bonddesk.oms.strategy.TwapExecution;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.stream.Stream;

/**
 * Replays a recorded full-depth L2 session and drives a strategy through it — reconstructing
 * the order book event-by-event over virtual time, ticking the strategy on a cadence, and
 * accounting P&L. Crucially it reuses the <em>live</em> execution seam ({@link Strategy},
 * {@link StrategyContext}, {@link com.bonddesk.oms.strategy.ExecutionModel} sweep,
 * {@link PnlBook}), so the exact code that trades live also runs in backtest.
 *
 * <p>Phase 1 (this class) establishes the replay spine with a sweep fill against real
 * recorded depth (honest multi-level slippage). The realistic microstructure fill model
 * (queue position, adverse selection, latency, our own market impact) layers on in later
 * phases — see MARKET-REALISM.md.
 */
@Service
public class BacktestService {

    private static final Logger log = LoggerFactory.getLogger(BacktestService.class);
    private static final int VOL_WINDOW = 60;

    private final CoinbaseProperties props;

    public BacktestService(CoinbaseProperties props) {
        this.props = props;
    }

    public BacktestResult run(BacktestRequest req) {
        if (req.product() == null || req.product().isBlank()) {
            throw new BadRequestException("product is required");
        }
        boolean buy = !"SELL".equalsIgnoreCase(req.side());
        Strategy strategy = build(req, buy);
        String product = req.product();
        long tickMs = req.tickMs() != null ? req.tickMs() : 500L;
        Path file = resolveFile(req.date());

        LiveOrderBook book = new LiveOrderBook(product);
        StrategyRun run = null;
        Instant nextTick = null;
        Instant firstTs = null;
        Instant lastTs = null;
        boolean started = false;
        boolean tradingDone = false;
        boolean arrivalSet = false;
        Deque<Double> mids = new ArrayDeque<>();
        double volSinceTick = 0;
        long events = 0;
        long ticks = 0;

        // Snapshot rows for one snapshot event share a sequence and are contiguous.
        List<Level> snapBids = new ArrayList<>();
        List<Level> snapAsks = new ArrayList<>();
        long snapSeq = Long.MIN_VALUE;
        boolean inSnap = false;

        try (BufferedReader r = Files.newBufferedReader(file)) {
            r.readLine(); // header
            String line;
            while ((line = r.readLine()) != null) {
                L2Event e = parse(line);
                if (e == null || !product.equals(e.product())) {
                    continue;
                }
                events++;
                if (firstTs == null) {
                    firstTs = e.ts();
                }
                lastTs = e.ts();
                if (run == null) {
                    run = new StrategyRun(strategy.type(), product, strategy, e.ts());
                }

                if (e.isSnapshot()) {
                    if (!inSnap || e.seq() != snapSeq) {
                        if (inSnap) {
                            book.resetTo(snapBids, snapAsks);
                        }
                        snapBids = new ArrayList<>();
                        snapAsks = new ArrayList<>();
                        snapSeq = e.seq();
                        inSnap = true;
                    }
                    (e.isBid() ? snapBids : snapAsks).add(new Level(e.price(), e.size()));
                    continue; // never tick mid-snapshot
                }

                if (inSnap) {
                    book.resetTo(snapBids, snapAsks);
                    inSnap = false;
                }
                if (e.isUpdate()) {
                    book.apply(e.isBid(), e.price(), e.size());
                } else if (e.isTrade()) {
                    volSinceTick += e.size().doubleValue();
                }

                // Advance the strategy on the tick cadence, in virtual (event) time.
                // Once the strategy is done we stop ticking but keep replaying so the final
                // book still marks the resulting position.
                if (!started && book.isReady()) {
                    nextTick = e.ts();
                    started = true;
                }
                while (started && !tradingDone && !e.ts().isBefore(nextTick) && book.isReady()) {
                    double mid = d(book.mid());
                    if (!arrivalSet && mid > 0) {
                        run.setArrivalMid(mid);
                        arrivalSet = true;
                    }
                    MarketState state = new MarketState(product, d(book.bestBid()), d(book.bestAsk()),
                            mid, d(book.microprice()), perTickSigma(mids), volSinceTick);
                    strategy.step(new StrategyContext(state, book, run, e.ts()));
                    run.touch(e.ts());
                    ticks++;
                    if (mid > 0) {
                        mids.addLast(mid);
                        while (mids.size() > VOL_WINDOW) {
                            mids.removeFirst();
                        }
                    }
                    volSinceTick = 0;
                    nextTick = nextTick.plusMillis(tickMs);
                    if (strategy.isDone()) {
                        tradingDone = true;
                    }
                }
            }
            if (inSnap) {
                book.resetTo(snapBids, snapAsks);
            }
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }

        if (run == null) {
            throw new BadRequestException("No events for product " + product + " in " + file.getFileName());
        }
        return buildResult(req, product, buy, book, run, events, ticks, firstTs, lastTs);
    }

    private BacktestResult buildResult(BacktestRequest req, String product, boolean buy, LiveOrderBook book,
                                       StrategyRun run, long events, long ticks, Instant start, Instant end) {
        double execSize = run.executedSize();
        double execNotional = run.executedNotional();
        double avgExec = execSize > 0 ? execNotional / execSize : 0;
        double arrival = run.arrivalMid();
        double isBps = (arrival > 0 && execSize > 0)
                ? (buy ? avgExec - arrival : arrival - avgExec) / arrival * 10_000.0 : 0;

        double finalMark = d(book.mid());
        PnlBook pnl = run.book();
        List<FillView> fills = pnl.fills().stream()
                .map(f -> new FillView(f.time(), f.side(), f.price(), f.size(), f.liquidity()))
                .toList();
        String note = execSize + 1e-9 < (req.size() == null ? 0 : req.size())
                ? "Partial: the recorded session ended before the schedule completed."
                : "Fills sweep real recorded depth (multi-level slippage); own-order market impact arrives in a later phase.";

        return new BacktestResult(product, run.type(), buy ? "BUY" : "SELL",
                req.size() == null ? 0 : req.size(), execSize, round(avgExec, 8), round(arrival, 8),
                round(isBps, 2), round(finalMark, 8), pnl.position(),
                round(pnl.realized(), 2), round(pnl.unrealized(finalMark), 2), round(pnl.totalPnl(finalMark), 2),
                fills.size(), events, ticks, start, end, note, fills);
    }

    private Strategy build(BacktestRequest req, boolean buy) {
        double size = req.size() == null ? 1.0 : req.size();
        int slices = req.slices() == null ? 10 : Math.max(1, req.slices());
        String type = req.strategyType() == null ? "TWAP" : req.strategyType().toUpperCase();
        return switch (type) {
            case "TWAP" -> new TwapExecution(buy, size, slices);
            case "POV" -> new PovExecution(buy, size, slices, req.participation() == null ? 0.1 : req.participation());
            case "ALMGREN_CHRISS" ->
                    new AlmgrenChrissExecution(buy, size, slices, req.kappa() == null ? 0.3 : req.kappa());
            case "AVELLANEDA_STOIKOV" -> throw new BadRequestException(
                    "Market-making backtest needs the maker fill model (Phase 2); execution algos (TWAP/POV/ALMGREN_CHRISS) work now");
            default -> throw new BadRequestException("Unknown strategyType: " + type);
        };
    }

    private Path resolveFile(String date) {
        Path dir = Path.of(props.getL2CaptureDir());
        if (date != null && !date.isBlank()) {
            Path f = dir.resolve("l2-" + date + ".csv");
            if (!Files.exists(f)) {
                throw new NotFoundException("No capture file for " + date + " at " + f);
            }
            return f;
        }
        if (!Files.isDirectory(dir)) {
            throw new NotFoundException("No L2 capture directory at " + dir.toAbsolutePath()
                    + " — run the backend with the crypto feed to record L2 first");
        }
        try (Stream<Path> files = Files.list(dir)) {
            return files.filter(p -> p.getFileName().toString().matches("l2-.*\\.csv"))
                    .max((a, b) -> a.getFileName().toString().compareTo(b.getFileName().toString()))
                    .orElseThrow(() -> new NotFoundException("No L2 capture files in " + dir.toAbsolutePath()));
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    private static L2Event parse(String line) {
        try {
            String[] f = line.split(",", 7);
            if (f.length < 7) {
                return null;
            }
            return new L2Event(Long.parseLong(f[0]), Instant.parse(f[1]), f[2], f[3], f[4],
                    new BigDecimal(f[5]), new BigDecimal(f[6]));
        } catch (RuntimeException ex) {
            return null; // skip malformed lines
        }
    }

    private static double perTickSigma(Deque<Double> mids) {
        if (mids.size() < 2) {
            return 0;
        }
        Double[] a = mids.toArray(new Double[0]);
        double mean = 0;
        double[] rets = new double[a.length - 1];
        for (int i = 1; i < a.length; i++) {
            rets[i - 1] = Math.log(a[i] / a[i - 1]);
            mean += rets[i - 1];
        }
        mean /= rets.length;
        double var = 0;
        for (double r : rets) {
            var += (r - mean) * (r - mean);
        }
        return Math.sqrt(var / rets.length);
    }

    private static double d(BigDecimal v) {
        return v == null ? 0 : v.doubleValue();
    }

    private static double round(double v, int dp) {
        double scale = Math.pow(10, dp);
        return Math.round(v * scale) / scale;
    }
}
