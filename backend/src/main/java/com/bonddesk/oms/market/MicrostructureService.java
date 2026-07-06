package com.bonddesk.oms.market;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedDeque;

/**
 * Keeps a rolling, in-memory window of microstructure signals per product (order-book
 * imbalance, microprice premium, spread) sampled once a second — the data behind the live
 * "Signals" view. In-memory and bounded; the CSV recorder is the durable capture path.
 */
@Service
public class MicrostructureService {

    private static final int WINDOW = 180; // ~3 minutes at 1 Hz

    private final MarketDataService marketData;
    private final Clock clock;
    private final Map<String, Deque<MicroSnapshot>> series = new ConcurrentHashMap<>();

    public MicrostructureService(MarketDataService marketData, Clock clock) {
        this.marketData = marketData;
        this.clock = clock;
    }

    @Scheduled(fixedDelay = 1000)
    public void sample() {
        for (String product : marketData.products()) {
            LiveOrderBook book = marketData.book(product);
            if (!book.isReady() || book.bestBidSize() == null || book.bestAskSize() == null) {
                continue;
            }
            double mid = book.mid().doubleValue();
            double micro = book.microprice() != null ? book.microprice().doubleValue() : mid;
            double bs = book.bestBidSize().doubleValue();
            double as = book.bestAskSize().doubleValue();
            double imbalance = (bs + as) == 0 ? 0 : (bs - as) / (bs + as);
            double spreadBps = mid == 0 ? 0 : (book.bestAsk().doubleValue() - book.bestBid().doubleValue()) / mid * 1e4;
            double microPremiumBps = mid == 0 ? 0 : (micro - mid) / mid * 1e4;

            Deque<MicroSnapshot> q = series.computeIfAbsent(product, k -> new ConcurrentLinkedDeque<>());
            q.addLast(new MicroSnapshot(clock.millis(), round(mid, 2), round(micro, 2),
                    round(imbalance, 4), round(spreadBps, 3), round(microPremiumBps, 3)));
            while (q.size() > WINDOW) {
                q.pollFirst();
            }
        }
    }

    public List<MicroSnapshot> series(String product) {
        Deque<MicroSnapshot> q = series.get(product);
        return q == null ? List.of() : new ArrayList<>(q);
    }

    private static double round(double v, int dp) {
        double f = Math.pow(10, dp);
        return Math.round(v * f) / f;
    }
}
