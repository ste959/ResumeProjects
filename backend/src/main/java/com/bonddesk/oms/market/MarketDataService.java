package com.bonddesk.oms.market;

import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

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

    public MarketDataService(CoinbaseProperties props) {
        this.props = props;
    }

    public LiveOrderBook book(String product) {
        return books.computeIfAbsent(product, LiveOrderBook::new);
    }

    public List<String> products() {
        return props.getProducts();
    }

    public void recordTrade(TradePrint print) {
        lastPrice.put(print.product(), print.price());
        Deque<TradePrint> tape = tapes.computeIfAbsent(print.product(), k -> new ArrayDeque<>());
        synchronized (tape) {
            tape.addFirst(print);
            while (tape.size() > props.getTradeTapeSize()) {
                tape.removeLast();
            }
        }
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
}
