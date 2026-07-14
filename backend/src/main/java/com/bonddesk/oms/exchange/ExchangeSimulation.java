package com.bonddesk.oms.exchange;

import com.bonddesk.exchange.CompositeListener;
import com.bonddesk.exchange.ExchangeListener;
import com.bonddesk.exchange.MakerAnalytics;
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
    private final MakerAnalytics makerAnalytics = new MakerAnalytics(mm);
    private final FlowGenerator flow = new FlowGenerator(11, 6, 0.35);
    private final Recorder rec = new Recorder();
    private final OrderBook book =
            new OrderBook(INSTRUMENT, new CompositeListener(List.of(mm, makerAnalytics, rec)), System::nanoTime);

    private long fair = FALLBACK_FAIR;
    private long tickCount;
    private long lastOrders;
    private double ordersPerSec;
    private long peakOrdersPerSec, p50LatencyNs, p99LatencyNs, maxLatencyNs;
    private List<ExchangeDtos.LatencyBucket> latencyBuckets = List.of();
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
                tickCount++;
                makerAnalytics.beginTick(tickCount, midTicks(), spreadTicks());
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
            tickCount++;
            makerAnalytics.beginTick(tickCount, midTicks(), spreadTicks());  // reference mid + mark out matured fills
            flow.step(book, fair, fair - prev, INTENSITY);   // flow hits the maker's stale quote
            mm.requote(book, fair);                          // maker refreshes
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

    // ── observability accessors (metrics gauges + health indicator) ─────────────────────────────
    /** Cumulative orders accepted by the book (monotonic — a benign single-long read). */
    public long acceptedOrders() { return book.orderCount(); }
    /** Cumulative trades matched (monotonic). */
    public long trades() { return book.tradeCount(); }
    public double ordersPerSec() { return ordersPerSec; }
    public long p50LatencyNanos() { return p50LatencyNs; }
    public long p99LatencyNanos() { return p99LatencyNs; }

    /** True if the engine has a live two-sided book — read under the engine lock to avoid racing the tick. */
    public boolean twoSided() {
        lock.lock();
        try {
            return book.bestBid() != null && book.bestAsk() != null;
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

    // ── analytics ───────────────────────────────────────────────────────────────────────────────
    public ExchangeDtos.AnalyticsView analytics() {
        lock.lock();
        try {
            double totalUsd = mm.pnl(fair) * TICK * LOT;
            double spreadUsd = makerAnalytics.sumEdgeTickLots() * TICK * LOT;
            double adverseUsd = makerAnalytics.sumAdverseTickLots() * TICK * LOT;
            double inventoryUsd = totalUsd - spreadUsd - adverseUsd;
            ExchangeDtos.PnlAttribution pnl = new ExchangeDtos.PnlAttribution(
                    r2(totalUsd), r2(spreadUsd), r2(adverseUsd), r2(inventoryUsd), makerAnalytics.markedOut());

            List<ExchangeDtos.FillView> fills = new ArrayList<>();
            double edgeSum = 0, moSum = 0;
            int moCount = 0;
            for (MakerAnalytics.Fill f : makerAnalytics.recentFills(60)) {
                double edgeBps = f.mid0Ticks > 0 ? f.edgeTicks / f.mid0Ticks * 1e4 : 0;
                Double moBps = (f.markoutTicks != null && f.mid0Ticks > 0) ? f.markoutTicks / f.mid0Ticks * 1e4 : null;
                double spreadBps = f.mid0Ticks > 0 ? (double) f.spreadTicks / f.mid0Ticks * 1e4 : 0;
                fills.add(new ExchangeDtos.FillView(f.seq, f.tick, f.mmBought ? "BUY" : "SELL",
                        f.priceTicks * TICK, f.sizeLots * LOT, aggrLabel(f.aggr), r1(spreadBps),
                        r4(f.invAfterLots * LOT), r2(edgeBps), moBps == null ? null : r2(moBps)));
                edgeSum += edgeBps;
                if (moBps != null) { moSum += moBps; moCount++; }
            }
            int nF = fills.size();
            ExchangeDtos.LatencyReport latency = new ExchangeDtos.LatencyReport(p50LatencyNs, p99LatencyNs,
                    maxLatencyNs, latencyBuckets,
                    "Match latency scales with how many resting orders a submit sweeps — the tail is large market orders walking the book.");
            long fc = makerAnalytics.fillCount();
            ExchangeDtos.Summary summary = new ExchangeDtos.Summary(fc, makerAnalytics.adverseCount(),
                    fc > 0 ? r4((double) makerAnalytics.informedFills() / fc) : 0,
                    nF > 0 ? r2(edgeSum / nF) : 0, moCount > 0 ? r2(moSum / moCount) : 0);
            return new ExchangeDtos.AnalyticsView(pnl, latency, fills, summary);
        } finally {
            lock.unlock();
        }
    }

    private static String aggrLabel(char c) {
        return switch (c) { case 'I' -> "INFORMED"; case 'N' -> "NOISE"; case 'Y' -> "YOU"; default -> "OTHER"; };
    }

    private long midTicks() {
        Long b = book.bestBid(), a = book.bestAsk();
        return (b != null && a != null) ? (b + a) / 2 : fair;
    }

    private long spreadTicks() {
        Long b = book.bestBid(), a = book.bestAsk();
        return (b != null && a != null) ? (a - b) : 0;
    }

    private static double r1(double v) { return Math.round(v * 10) / 10.0; }
    private static double r2(double v) { return Math.round(v * 100) / 100.0; }
    private static double r4(double v) { return Math.round(v * 1e4) / 1e4; }

    // ── boot benchmark (engine capability, latency by match depth) ──────────────────────────────
    private void benchmark() {
        OrderBook b = new OrderBook("BENCH");
        Random r = new Random(1);
        long mid = 50_000;
        int n = 200_000;
        for (int warm = 0; warm < 50_000; warm++) { mid += r.nextInt(3) - 1; benchOp(b, r, mid, null, null, 0); }
        long[] lat = new long[n];
        int[] depth = new int[n];
        long start = System.nanoTime();
        for (int i = 0; i < n; i++) { mid += r.nextInt(3) - 1; benchOp(b, r, mid, lat, depth, i); }
        double sec = (System.nanoTime() - start) / 1e9;
        peakOrdersPerSec = (long) (n / sec);
        long[] sorted = lat.clone();
        Arrays.sort(sorted);
        p50LatencyNs = sorted[n / 2];
        p99LatencyNs = sorted[(int) (n * 0.99)];
        maxLatencyNs = sorted[n - 1];
        latencyBuckets = List.of(
                bucket("no match", lat, depth, 0, 0),
                bucket("shallow (1–2)", lat, depth, 1, 2),
                bucket("mid (3–5)", lat, depth, 3, 5),
                bucket("deep sweep (6+)", lat, depth, 6, Integer.MAX_VALUE));
    }

    private void benchOp(OrderBook b, Random r, long mid, long[] lat, int[] depth, int i) {
        long t0 = lat != null ? System.nanoTime() : 0;
        int d;
        double u = r.nextDouble();
        if (u < 0.2) {
            d = b.submit("t" + (i & 7), r.nextBoolean() ? Side.BUY : Side.SELL, OrderType.MARKET, TimeInForce.IOC, false, 0, 1 + r.nextInt(5)).trades().size();
        } else {
            Side s = r.nextBoolean() ? Side.BUY : Side.SELL;
            long px = s == Side.BUY ? mid - 1 - r.nextInt(5) : mid + 1 + r.nextInt(5);
            d = b.submit("m" + (i & 15), s, OrderType.LIMIT, TimeInForce.GTC, false, px, 1 + r.nextInt(9)).trades().size();
        }
        if (lat != null) { lat[i] = System.nanoTime() - t0; depth[i] = d; }
    }

    private static ExchangeDtos.LatencyBucket bucket(String label, long[] lat, int[] depth, int lo, int hi) {
        long[] tmp = new long[lat.length];
        int m = 0;
        for (int i = 0; i < lat.length; i++) {
            if (depth[i] >= lo && depth[i] <= hi) tmp[m++] = lat[i];
        }
        if (m == 0) return new ExchangeDtos.LatencyBucket(label, 0, 0, 0);
        long[] s = Arrays.copyOf(tmp, m);
        Arrays.sort(s);
        return new ExchangeDtos.LatencyBucket(label, s[m / 2], s[(int) (m * 0.99)], m);
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
