package com.bonddesk.oms.equities;

import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * In-memory store of live equity market data, written by {@link AlpacaFeedClient} and
 * read by the controller and any pre-trade pricing. Mirrors the crypto
 * {@code MarketDataService}, but holds a single NBBO quote per symbol (the free IEX feed
 * is top-of-book) plus a rolling trade tape.
 */
@Service
public class EquityMarketDataService {

    private final AlpacaProperties props;

    private final Map<String, EquityQuote> quotes = new ConcurrentHashMap<>();
    private final Map<String, Deque<EquityTrade>> tapes = new ConcurrentHashMap<>();
    private final Map<String, BigDecimal> lastPrice = new ConcurrentHashMap<>();
    private final AtomicLong tradeSeq = new AtomicLong();

    public EquityMarketDataService(AlpacaProperties props) {
        this.props = props;
    }

    public List<String> symbols() {
        return props.getSymbols();
    }

    /** Apply a top-of-book quote update, preserving the last traded price. */
    public void updateQuote(String symbol, BigDecimal bid, BigDecimal ask,
                            BigDecimal bidSize, BigDecimal askSize, Instant time) {
        quotes.put(symbol, new EquityQuote(symbol, bid, ask, bidSize, askSize,
                lastPrice.get(symbol), time));
    }

    /** Record a trade print, update the last price, and refresh the quote's last field. */
    public void recordTrade(String symbol, BigDecimal price, BigDecimal size, Instant time) {
        lastPrice.put(symbol, price);
        Deque<EquityTrade> tape = tapes.computeIfAbsent(symbol, s -> new ArrayDeque<>());
        synchronized (tape) {
            tape.addFirst(new EquityTrade(tradeSeq.incrementAndGet(), symbol, price, size, time));
            while (tape.size() > props.getTradeTapeSize()) {
                tape.removeLast();
            }
        }
        EquityQuote q = quotes.get(symbol);
        if (q != null) {
            quotes.put(symbol, new EquityQuote(symbol, q.bid(), q.ask(), q.bidSize(), q.askSize(), price, time));
        }
    }

    public EquityQuote quote(String symbol) {
        return quotes.get(symbol);
    }

    public List<EquityQuote> allQuotes() {
        List<EquityQuote> out = new ArrayList<>();
        for (String symbol : props.getSymbols()) {
            EquityQuote q = quotes.get(symbol);
            if (q != null) {
                out.add(q);
            }
        }
        return out;
    }

    public List<EquityTrade> recentTrades(String symbol) {
        Deque<EquityTrade> tape = tapes.get(symbol);
        if (tape == null) {
            return List.of();
        }
        synchronized (tape) {
            return new ArrayList<>(tape);
        }
    }

    public BigDecimal lastPrice(String symbol) {
        return lastPrice.get(symbol);
    }
}
