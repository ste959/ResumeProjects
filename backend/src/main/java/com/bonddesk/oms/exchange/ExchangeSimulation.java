package com.bonddesk.oms.exchange;

import com.bonddesk.exchange.CompositeListener;
import com.bonddesk.exchange.ExchangeListener;
import com.bonddesk.exchange.MarketMaker;
import com.bonddesk.exchange.FlowGenerator;
import com.bonddesk.exchange.Order;
import com.bonddesk.exchange.OrderBook;
import com.bonddesk.exchange.OrderType;
import com.bonddesk.exchange.Side;
import com.bonddesk.exchange.SubmitResult;
import com.bonddesk.exchange.TimeInForce;
import com.bonddesk.exchange.Trade;
import com.bonddesk.oms.exchange.ExchangeDtos.Level;
import com.bonddesk.oms.exchange.ExchangeDtos.PlaceRequest;
import com.bonddesk.oms.exchange.ExchangeDtos.PlaceResponse;
import com.bonddesk.oms.exchange.ExchangeDtos.QueueOrder;
import com.bonddesk.oms.exchange.ExchangeDtos.Snapshot;
import com.bonddesk.oms.exchange.ExchangeDtos.Stats;
import com.bonddesk.oms.exchange.ExchangeDtos.TradeView;
import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.MarketDataService;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;
import java.util.Random;
import java.util.concurrent.locks.ReentrantLock;

/**
 * The live exchange: our matching engine driven by an inventory-skewed market maker and an
 * agent-based order flow, with the fair price <b>anchored to the real Coinbase BTC mid</b> so the
 * level tracks reality while the microstructure (orders, queues, matches) is genuinely ours. Ticks
 * on a timer; a lock serialises the tick loop with user order entry so the single-threaded engine is
 * never touched concurrently. Publishes a market-data snapshot each tick and benchmarks the engine
 * once at boot for the throughput/latency stats.
 */
@Service
public class ExchangeSimulation {

    private static final String INSTRUMENT = "BTC-USD";
    private static final double TICK = 1.0;      // $1 per tick
    private static final double LOT = 0.001;     // 0.001 BTC per lot
    private static final int INTENSITY = 8;      // agent orders per tick
    private static final long FALLBACK_FAIR = 60_000;

    private final ObjectProvider<MarketDataService> marketData;
    private final ExchangeSocketHandler socket;
    private final ObjectMapper mapper;

    private final ReentrantLock lock = new ReentrantLock();
    private final Random rng = new Random(7);
    private final MarketMaker mm = new MarketMaker(3, 1, 15, 400);
    private final FlowGenerator flow = new FlowGenerator(11, 6, 0.35);
    private final Recorder rec = new Recorder();
    private final OrderBook book =
            new OrderBook(INSTRUMENT, new CompositeListener(List.of(mm, rec)), System::nanoTime);

    private long fair = FALLBACK_FAIR;
    private long tickCount;
    private long lastOrders;
    private double ordersPerSec;
    private long peakOrdersPerSec, p50LatencyNs, p99LatencyNs;
    private volatile Snapshot latest;

    public ExchangeSimulation(ObjectProvider<MarketDataService> marketData,
                              ExchangeSocketHandler socket, ObjectMapper mapper) {
        this.marketData = marketData;
        this.socket = socket;
        this.mapper = mapper;
    }

    @PostConstruct
    void init() {
        benchmark();                                   // measure engine capability (throughput / latency)
        lock.lock();
        try {
            for (int i = 0; i < 60; i++) {             // seed a live book before the first client connects
                evolveFair();
                flow.step(book, fair, 0, INTENSITY);
                mm.requote(book, fair);
            }
            latest = buildSnapshot();
        } finally {
            lock.unlock();
        }
    }

    @Scheduled(fixedDelay = 100)
    public void tick() {
        Snapshot snap;
        lock.lock();
        try {
            long prev = fair;
            evolveFair();
            flow.step(book, fair, fair - prev, INTENSITY);   // flow hits the maker's stale quote
            mm.requote(book, fair);                          // maker refreshes
            tickCount++;
            updateThroughput();
            snap = buildSnapshot();
        } finally {
            lock.unlock();
        }
        latest = snap;
        try {
            socket.broadcast(mapper.writeValueAsString(snap));
        } catch (Exception ignored) {
            // serialization/push failure is non-fatal to the engine
        }
    }

    // ── order entry (user) ──────────────────────────────────────────────────────────────────────
    public PlaceResponse place(PlaceRequest req) {
        Side side = "SELL".equalsIgnoreCase(req.side()) ? Side.SELL : Side.BUY;
        OrderType type = "MARKET".equalsIgnoreCase(req.type()) ? OrderType.MARKET : OrderType.LIMIT;
        TimeInForce tif = type == OrderType.MARKET ? TimeInForce.IOC
                : switch (req.tif() == null ? "GTC" : req.tif().toUpperCase()) {
                    case "IOC" -> TimeInForce.IOC;
                    case "FOK" -> TimeInForce.FOK;
                    default -> TimeInForce.GTC;
                };
        long qtyLots = Math.max(1, Math.round((req.size() == null ? LOT : req.size()) / LOT));
        long priceTicks = type == OrderType.LIMIT && req.price() != null ? Math.round(req.price() / TICK) : 0;

        lock.lock();
        try {
            SubmitResult r = book.submit("YOU", side, type, tif, req.postOnly(), priceTicks, qtyLots);
            return new PlaceResponse(r.orderId(), r.status().name(), r.reason(), r.trades().size(),
                    r.filledQty() * LOT, r.restingQty() * LOT);
        } finally {
            lock.unlock();
        }
    }

    public boolean cancel(long orderId) {
        lock.lock();
        try {
            return book.cancel(orderId);
        } finally {
            lock.unlock();
        }
    }

    public Snapshot snapshot() {
        Snapshot s = latest;
        if (s != null) {
            return s;
        }
        lock.lock();
        try {
            return buildSnapshot();
        } finally {
            lock.unlock();
        }
    }

    // ── fair price (anchored to real BTC when the feed is live) ─────────────────────────────────
    private void evolveFair() {
        Long real = realMidTicks();
        long walk = rng.nextInt(3) - 1;                        // micro random walk (short-term flow)
        long anchor = real != null ? real : FALLBACK_FAIR;     // pull toward the real level (or fallback)
        long pull = (long) Math.signum((double) (anchor - fair)) * Math.min(Math.abs(anchor - fair), 3);
        fair = Math.max(1000, fair + walk + pull);
    }

    private Long realMidTicks() {
        MarketDataService md = marketData.getIfAvailable();
        if (md == null) {
            return null;
        }
        LiveOrderBook b = md.book(INSTRUMENT);
        BigDecimal mid = b != null ? b.mid() : null;
        return mid != null ? Math.round(mid.doubleValue() / TICK) : null;
    }

    // ── snapshot ────────────────────────────────────────────────────────────────────────────────
    private Snapshot buildSnapshot() {
        return new Snapshot(INSTRUMENT, TICK, LOT, tickCount, buildStats(),
                levels(Side.BUY, 14), levels(Side.SELL, 14),
                queue(Side.BUY, 12), queue(Side.SELL, 12), tradeViews());
    }

    private List<Level> levels(Side side, int n) {
        long mmPx = side == Side.BUY ? mm.quoteBidTicks() : mm.quoteAskTicks();
        List<Level> out = new ArrayList<>();
        for (long[] row : book.l2(side, n)) {
            out.add(new Level(row[0] * TICK, row[1] * LOT, (int) row[2], row[0] == mmPx, false));
        }
        return out;
    }

    private List<QueueOrder> queue(Side side, int n) {
        List<QueueOrder> out = new ArrayList<>();
        for (Order o : book.l3(side, n)) {
            String owner = switch (o.participant()) {
                case "MM" -> "MM";
                case "YOU" -> "YOU";
                default -> "FLOW";
            };
            out.add(new QueueOrder(o.id(), o.priceTicks() * TICK, o.remaining() * LOT, owner));
        }
        return out;
    }

    private List<TradeView> tradeViews() {
        List<TradeView> out = new ArrayList<>();
        synchronized (rec.trades) {
            for (Trade t : rec.trades) {
                out.add(new TradeView(t.seq(), t.priceTicks() * TICK, t.qty() * LOT,
                        t.aggressorSide().name(), label(t.makerParticipant()), label(t.takerParticipant())));
            }
        }
        return out;
    }

    private static String label(String p) {
        return switch (p) { case "MM" -> "MM"; case "YOU" -> "YOU"; default -> "FLOW"; };
    }

    private Stats buildStats() {
        Long bid = book.bestBid(), ask = book.bestAsk();
        double mid = (bid != null && ask != null) ? (bid + ask) / 2.0 * TICK : fair * TICK;
        Double spreadBps = (bid != null && ask != null && mid > 0) ? (ask - bid) * TICK / mid * 1e4 : null;
        long invLots = mm.inventory();
        double pnlUsd = mm.pnl(fair) * TICK * LOT;
        return new Stats(fair * TICK, mid, spreadBps, invLots, invLots * LOT, pnlUsd, mm.fills(),
                ordersPerSec, book.tradeCount(), peakOrdersPerSec, p50LatencyNs, p99LatencyNs,
                book.restingQuantity() * LOT);
    }

    private void updateThroughput() {
        long delta = rec.orders - lastOrders;
        lastOrders = rec.orders;
        double inst = delta / 0.1;                             // orders in the last ~100ms tick
        ordersPerSec = ordersPerSec == 0 ? inst : 0.7 * ordersPerSec + 0.3 * inst;   // EMA
    }

    // ── boot benchmark (engine capability) ──────────────────────────────────────────────────────
    private void benchmark() {
        OrderBook b = new OrderBook("BENCH");
        Random r = new Random(1);
        long mid = 50_000;
        int n = 200_000;
        for (int warm = 0; warm < 50_000; warm++) benchOp(b, r, mid += r.nextInt(3) - 1, null, 0);
        long[] lat = new long[n];
        long start = System.nanoTime();
        for (int i = 0; i < n; i++) benchOp(b, r, mid += r.nextInt(3) - 1, lat, i);
        double sec = (System.nanoTime() - start) / 1e9;
        peakOrdersPerSec = (long) (n / sec);
        Arrays.sort(lat);
        p50LatencyNs = lat[n / 2];
        p99LatencyNs = lat[(int) (n * 0.99)];
    }

    private void benchOp(OrderBook b, Random r, long mid, long[] lat, int i) {
        long t0 = lat != null ? System.nanoTime() : 0;
        double u = r.nextDouble();
        if (u < 0.2) {
            b.submit("t" + (i & 7), r.nextBoolean() ? Side.BUY : Side.SELL, OrderType.MARKET, TimeInForce.IOC, false, 0, 1 + r.nextInt(5));
        } else {
            Side s = r.nextBoolean() ? Side.BUY : Side.SELL;
            long px = s == Side.BUY ? mid - 1 - r.nextInt(5) : mid + 1 + r.nextInt(5);
            b.submit("m" + (i & 15), s, OrderType.LIMIT, TimeInForce.GTC, false, px, 1 + r.nextInt(9));
        }
        if (lat != null) lat[i] = System.nanoTime() - t0;
    }

    /** Records trades (for the tape) and counts accepted orders (for throughput). */
    private static final class Recorder implements ExchangeListener {
        final Deque<Trade> trades = new ArrayDeque<>();
        volatile long orders;

        @Override public void onAccepted(Order o) { orders++; }

        @Override public void onTrade(Trade t) {
            synchronized (trades) {
                trades.addFirst(t);
                while (trades.size() > 50) trades.removeLast();
            }
        }
    }
}
