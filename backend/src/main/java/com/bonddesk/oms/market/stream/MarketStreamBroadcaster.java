package com.bonddesk.oms.market.stream;

import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.LiveOrderBook.Level;
import com.bonddesk.oms.market.MarketDataService;
import com.bonddesk.oms.market.PaperTradingService;
import com.bonddesk.oms.market.TradePrint;
import com.bonddesk.oms.market.dto.MarketDtos.DepthLevel;
import com.bonddesk.oms.market.dto.MarketDtos.PaperOrder;
import com.bonddesk.oms.market.dto.MarketDtos.ProductQuote;
import com.bonddesk.oms.market.stream.MarketSocketHandler.Subscription;
import com.bonddesk.oms.market.stream.StreamFrames.BookFrame;
import com.bonddesk.oms.market.stream.StreamFrames.Metrics;
import com.bonddesk.oms.market.stream.StreamFrames.MetricsFrame;
import com.bonddesk.oms.market.stream.StreamFrames.TradeFrame;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;

/**
 * Pushes the live market-data stream to WebSocket subscribers on a fixed timer. This is deliberately
 * a single scheduled loop rather than a hook on the feed thread: it reads the same thread-safe
 * services the REST controller does, keeps the feed callback cheap, and bounds bandwidth to a few
 * frames per second regardless of how fast the exchange updates the book.
 *
 * <p>Per tick, for each subscriber it sends: a depth-ladder {@code book} frame, a {@code trade} frame
 * with the prints since that client's cursor, and a {@code metrics} frame (book/trade throughput,
 * imbalance, microprice premium, spread, book age, and paper-trading fill/slippage stats).
 */
@Service
@ConditionalOnProperty(name = "oms.crypto.enabled", matchIfMissing = true)
public class MarketStreamBroadcaster {

    private static final int DEPTH = 12;
    private static final BigDecimal BPS = BigDecimal.valueOf(10_000);

    private final MarketSocketHandler handler;
    private final MarketDataService marketData;
    private final PaperTradingService paper;
    private final Clock clock;

    public MarketStreamBroadcaster(MarketSocketHandler handler, MarketDataService marketData,
                                   PaperTradingService paper, Clock clock) {
        this.handler = handler;
        this.marketData = marketData;
        this.paper = paper;
        this.clock = clock;
    }

    @Scheduled(fixedDelay = 250)
    public void broadcast() {
        long now = clock.millis();
        for (Subscription sub : handler.subscriptions()) {
            String product = sub.product();
            if (product == null) {
                continue;
            }
            LiveOrderBook book = marketData.book(product);

            // 1. Book ladder + top-of-book quote.
            handler.send(sub, new BookFrame(product, quote(product, book),
                    ladder(book.depth(true, DEPTH)), ladder(book.depth(false, DEPTH))));

            // 2. New trade prints since this client's cursor (the order-flow tape).
            List<TradePrint> newTrades = marketData.tradesSince(product, sub.lastTradeSeq);
            if (!newTrades.isEmpty()) {
                sub.lastTradeSeq = newTrades.get(newTrades.size() - 1).seq();
                handler.send(sub, new TradeFrame(product, newTrades));
            }

            // 3. Metrics — throughput rates diff against the previous tick's counters.
            double intervalSec = sub.lastTickMillis == 0 ? 0.25 : Math.max(1, now - sub.lastTickMillis) / 1000.0;
            long updates = book.updateCount();
            double bookRate = sub.lastTickMillis == 0 ? 0.0 : (updates - sub.lastUpdateCount) / intervalSec;
            double tradeRate = newTrades.size() / intervalSec;
            sub.lastUpdateCount = updates;
            sub.lastTickMillis = now;
            handler.send(sub, new MetricsFrame(product, metrics(product, book, bookRate, tradeRate, now)));
        }
    }

    // ---- frame builders (mirror MarketController's quote/ladder) ----

    private ProductQuote quote(String product, LiveOrderBook book) {
        BigDecimal bid = book.bestBid();
        BigDecimal ask = book.bestAsk();
        BigDecimal mid = book.mid();
        BigDecimal spread = (bid == null || ask == null) ? null : ask.subtract(bid);
        BigDecimal spreadBps = (spread == null || mid == null || mid.signum() == 0) ? null
                : spread.divide(mid, 8, RoundingMode.HALF_UP).multiply(BPS).setScale(2, RoundingMode.HALF_UP);
        return new ProductQuote(product, bid, ask, mid, spread, spreadBps, marketData.lastPrice(product));
    }

    private List<DepthLevel> ladder(List<Level> levels) {
        List<DepthLevel> rows = new ArrayList<>(levels.size());
        BigDecimal cumulative = BigDecimal.ZERO;
        for (Level l : levels) {
            cumulative = cumulative.add(l.size());
            rows.add(new DepthLevel(l.price(), l.size(), cumulative));
        }
        return rows;
    }

    private Metrics metrics(String product, LiveOrderBook book, double bookRate, double tradeRate, long now) {
        BigDecimal bid = book.bestBid(), ask = book.bestAsk(), mid = book.mid(), micro = book.microprice();
        BigDecimal bbs = book.bestBidSize(), bas = book.bestAskSize();
        boolean ready = bid != null && ask != null && mid != null && bbs != null && bas != null;
        double m = ready ? mid.doubleValue() : 0.0;
        double bs = bbs != null ? bbs.doubleValue() : 0.0;
        double as = bas != null ? bas.doubleValue() : 0.0;
        double imbalance = (bs + as) == 0 ? 0.0 : (bs - as) / (bs + as);
        double spreadBps = ready && m != 0 ? (ask.doubleValue() - bid.doubleValue()) / m * 1e4 : 0.0;
        double microPremiumBps = (ready && micro != null && m != 0) ? (micro.doubleValue() - m) / m * 1e4 : 0.0;
        long bookAgeMs = book.lastUpdateMillis() == 0 ? -1 : now - book.lastUpdateMillis();

        // Paper-trading execution quality for this product (fill rate + realized slippage).
        int total = 0, filled = 0;
        double slipSum = 0.0;
        int slipN = 0;
        for (PaperOrder o : paper.recentOrders()) {
            if (!product.equals(o.product())) {
                continue;
            }
            total++;
            if (o.filledSize() != null && o.filledSize().signum() > 0) {
                filled++;
                if (o.slippageBps() != null) {
                    slipSum += o.slippageBps().doubleValue();
                    slipN++;
                }
            }
        }
        double fillRatePct = total == 0 ? 0.0 : 100.0 * filled / total;
        double avgSlippageBps = slipN == 0 ? 0.0 : slipSum / slipN;

        return new Metrics(ready, round(m, 2), round(ready && micro != null ? micro.doubleValue() : m, 2),
                round(imbalance, 4), round(spreadBps, 3), round(microPremiumBps, 3),
                round(bookRate, 1), round(tradeRate, 1), bookAgeMs,
                round(fillRatePct, 1), round(avgSlippageBps, 2), total);
    }

    private static double round(double v, int dp) {
        double f = Math.pow(10, dp);
        return Math.round(v * f) / f;
    }
}
