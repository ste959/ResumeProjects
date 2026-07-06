package com.bonddesk.oms.strategy;

import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.MarketDataService;
import com.bonddesk.oms.market.TradePrint;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Drives every active strategy once per tick: assembles the market state (top of book,
 * microprice, a rolling volatility estimate and recent traded volume), steps the strategy,
 * then applies the maker fill model — a resting quote is filled when a real trade prints
 * through it. Single-threaded by design (one scheduler thread).
 */
@Component
@ConditionalOnProperty(prefix = "oms.crypto", name = "enabled", havingValue = "true", matchIfMissing = true)
public class StrategyRunner {

    private static final int VOL_WINDOW = 60;

    private final StrategyService strategies;
    private final MarketDataService marketData;
    private final Clock clock;

    private final Map<String, Deque<Double>> midHistory = new HashMap<>();
    private final Map<String, Long> volCursor = new HashMap<>();

    public StrategyRunner(StrategyService strategies, MarketDataService marketData, Clock clock) {
        this.strategies = strategies;
        this.marketData = marketData;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${oms.crypto.strategy-tick-ms:500}")
    public void tick() {
        List<StrategyRun> active = strategies.activeRuns();
        if (active.isEmpty()) {
            return;
        }
        Instant now = clock.instant();
        Map<String, MarketState> states = new HashMap<>();

        for (StrategyRun run : active) {
            MarketState state = states.computeIfAbsent(run.product(), this::buildState);
            if (state == null) {
                continue; // book not ready yet
            }
            LiveOrderBook book = marketData.book(run.product());
            run.strategy().step(new StrategyContext(state, book, run, now));
            applyMakerFills(run, now);
            run.touch(now);
            if (run.strategy().isDone()) {
                run.setStatus("DONE");
            }
        }
    }

    private MarketState buildState(String product) {
        LiveOrderBook book = marketData.book(product);
        if (!book.isReady()) {
            return null;
        }
        double bid = book.bestBid().doubleValue();
        double ask = book.bestAsk().doubleValue();
        double mid = book.mid().doubleValue();
        double micro = book.microprice() != null ? book.microprice().doubleValue() : mid;

        Deque<Double> hist = midHistory.computeIfAbsent(product, k -> new ArrayDeque<>());
        hist.addLast(mid);
        while (hist.size() > VOL_WINDOW) {
            hist.removeFirst();
        }
        double sigma = perTickSigma(hist);

        long cursor = volCursor.getOrDefault(product, marketData.currentTradeSeq());
        List<TradePrint> since = marketData.tradesSince(product, cursor);
        double volume = since.stream().mapToDouble(t -> t.size().doubleValue()).sum();
        if (!since.isEmpty()) {
            volCursor.put(product, since.get(since.size() - 1).seq());
        } else {
            volCursor.putIfAbsent(product, cursor);
        }
        return new MarketState(product, bid, ask, mid, micro, sigma, volume);
    }

    /** Standard deviation of mid log-returns over the window (per-tick volatility). */
    private static double perTickSigma(Deque<Double> mids) {
        if (mids.size() < 3) {
            return 0.0;
        }
        Double[] arr = mids.toArray(new Double[0]);
        double[] rets = new double[arr.length - 1];
        for (int i = 1; i < arr.length; i++) {
            rets[i - 1] = Math.log(arr[i] / arr[i - 1]);
        }
        double mean = 0;
        for (double r : rets) mean += r;
        mean /= rets.length;
        double var = 0;
        for (double r : rets) var += (r - mean) * (r - mean);
        return Math.sqrt(var / rets.length);
    }

    /** Fill resting quotes when a real trade prints through them (optimistic queue). */
    private void applyMakerFills(StrategyRun run, Instant now) {
        List<TradePrint> trades = marketData.tradesSince(run.product(), run.lastTradeSeq());
        for (TradePrint t : trades) {
            double price = t.price().doubleValue();
            double size = t.size().doubleValue();
            if (run.quoteSize() > 0) {
                if (price <= run.quoteBid()) {
                    double fill = Math.min(run.quoteSize(), size);
                    run.book().apply(Fill.maker(now, true, run.quoteBid(), fill));
                    run.reduceQuote(fill);
                } else if (price >= run.quoteAsk()) {
                    double fill = Math.min(run.quoteSize(), size);
                    run.book().apply(Fill.maker(now, false, run.quoteAsk(), fill));
                    run.reduceQuote(fill);
                }
            }
        }
        if (!trades.isEmpty()) {
            run.setLastTradeSeq(trades.get(trades.size() - 1).seq());
        }
    }
}
