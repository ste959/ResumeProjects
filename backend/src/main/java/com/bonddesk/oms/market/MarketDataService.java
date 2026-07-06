package com.bonddesk.oms.market;

import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Holds the live order book and recent trade tape for each subscribed product. The feed
 * client writes here from the WebSocket thread; controllers read from request threads.
 */
@Service
public class MarketDataService {

    private final CoinbaseProperties props;
    private final Map<String, LiveOrderBook> books = new ConcurrentHashMap<>();
    private final Map<String, Deque<TradePrint>> tapes = new ConcurrentHashMap<>();
    private final Map<String, BigDecimal> lastPrice = new ConcurrentHashMap<>();
    private final AtomicLong tradeSeq = new AtomicLong();

    public MarketDataService(CoinbaseProperties props) {
        this.props = props;
    }

    public LiveOrderBook book(String product) {
        return books.computeIfAbsent(product, LiveOrderBook::new);
    }

    public List<String> products() {
        return props.getProducts();
    }

    public void recordTrade(String product, BigDecimal price, BigDecimal size, String side, Instant time) {
        TradePrint print = new TradePrint(tradeSeq.incrementAndGet(), product, price, size, side, time);
        lastPrice.put(product, price);
        Deque<TradePrint> tape = tapes.computeIfAbsent(product, k -> new ArrayDeque<>());
        synchronized (tape) {
            tape.addFirst(print);
            while (tape.size() > props.getTradeTapeSize()) {
                tape.removeLast();
            }
        }
    }

    /** Trades newer than {@code afterSeq}, in chronological order. */
    public List<TradePrint> tradesSince(String product, long afterSeq) {
        Deque<TradePrint> tape = tapes.get(product);
        if (tape == null) {
            return List.of();
        }
        List<TradePrint> out = new ArrayList<>();
        synchronized (tape) {
            for (TradePrint t : tape) {  // newest first
                if (t.seq() > afterSeq) {
                    out.add(t);
                }
            }
        }
        Collections.reverse(out); // chronological
        return out;
    }

    public List<TradePrint> recentTrades(String product) {
        Deque<TradePrint> tape = tapes.get(product);
        if (tape == null) {
            return List.of();
        }
        synchronized (tape) {
            return new ArrayList<>(tape);
        }
    }

    public BigDecimal lastPrice(String product) {
        return lastPrice.get(product);
    }

    /** The newest trade sequence assigned so far (a cursor for "trades from now on"). */
    public long currentTradeSeq() {
        return tradeSeq.get();
    }
}
