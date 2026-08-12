package com.bonddesk.exchange;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.LongSupplier;

/**
 * A central-limit-order-book matching engine for one instrument, matching on strict
 * <b>price-time priority</b>: an aggressor trades against the best opposite price first, and within
 * a price level the earliest-resting order (lowest arrival sequence) fills first (FIFO).
 *
 * <p>Supported semantics — the things that separate a real engine from a toy:
 * <ul>
 *   <li><b>Order types</b>: LIMIT (rests) and MARKET (takes only).</li>
 *   <li><b>Time-in-force</b>: GTC (rest remainder), IOC (cancel remainder), FOK (all-or-nothing —
 *       rejected up-front if not fully fillable, so no partial print escapes).</li>
 *   <li><b>Post-only</b>: rejected if it would cross (guarantees the maker rebate / never takes).</li>
 *   <li><b>Self-trade prevention</b>: a participant never trades with itself — the resting order is
 *       cancelled (cancel-maker STP) instead of generating a wash print.</li>
 *   <li><b>Cancel / replace</b>: a pure size reduction keeps time priority; a price change or size
 *       increase re-queues at the back (the exchange-correct amend rule).</li>
 * </ul>
 *
 * <p>Data structure: price levels in {@link TreeMap}s (any level O(log n) to find), each level a
 * FIFO {@link ArrayDeque}; cancels are lazy (flag inactive, skip during matching) for O(1) cancels.
 * Top-of-book is cached and maintained on every mutation, so {@link #bestBid()}/{@link #bestAsk()}
 * are O(1) reads (a {@code TreeMap.firstKey()} would otherwise walk the tree). The hot path is
 * all-integer (tick prices, lot sizes); the common passive path — a limit order that rests without
 * trading — allocates nothing (the trade list is created lazily, only when a fill actually occurs).
 *
 * <p><b>Not thread-safe</b> by design — a single writer thread per book. Every engine event is
 * pushed to the {@link ExchangeListener} in execution order for the market-data feed and analytics.
 */
public final class OrderBook {

    /** One price level: a FIFO queue of orders plus the running active quantity resting there. */
    private static final class Level {
        final Deque<Order> orders = new ArrayDeque<>();
        long totalQty;
    }

    private final String instrument;
    private final ExchangeListener listener;
    private final LongSupplier clock;

    private final TreeMap<Long, Level> bids = new TreeMap<>(Comparator.reverseOrder()); // high → low
    private final TreeMap<Long, Level> asks = new TreeMap<>();                            // low → high
    private final Map<Long, Order> byId = new HashMap<>();

    // Cached top-of-book (null when a side is empty), refreshed after every mutation so best-price
    // reads are O(1) instead of an O(log n) TreeMap.firstKey() walk.
    private Long cachedBestBid;
    private Long cachedBestAsk;

    private long orderSeq;
    private long tradeSeq;
    private long totalOrders;
    private long totalTrades;

    public OrderBook(String instrument) {
        this(instrument, ExchangeListener.NOOP, System::nanoTime);
    }

    public OrderBook(String instrument, ExchangeListener listener, LongSupplier clock) {
        this.instrument = instrument;
        this.listener = listener;
        this.clock = clock;
    }

    // ─────────────────────────────────────────────────────────────────────────────────────────────
    // Submit
    // ─────────────────────────────────────────────────────────────────────────────────────────────
    public SubmitResult submit(String participant, Side side, OrderType type, TimeInForce tif,
                               boolean postOnly, long priceTicks, long qty) {
        long id = ++orderSeq;
        totalOrders++;

        String err = validate(type, tif, postOnly, priceTicks, qty);
        if (err != null) {
            listener.onRejected(id, participant, err);
            return reject(id, err);
        }

        Order order = new Order(id, id, participant, side, type, tif, postOnly, priceTicks, qty);
        listener.onAccepted(order);
        TreeMap<Long, Level> opposite = side == Side.BUY ? asks : bids;

        // Post-only must not take: reject if the best opposite price is already marketable.
        if (postOnly) {
            Map.Entry<Long, Level> best = opposite.firstEntry();
            if (best != null && crosses(order, best.getKey())) {
                listener.onRejected(id, participant, "post-only would cross");
                return reject(id, "post-only would cross");
            }
        }
        // Fill-or-kill: all-or-nothing, decided before any trade prints.
        if (tif == TimeInForce.FOK && marketableQty(order, opposite) < qty) {
            listener.onRejected(id, participant, "FOK not fully fillable");
            return reject(id, "FOK not fully fillable");
        }

        List<Trade> trades = match(order, opposite, null);

        long filled = qty - order.remaining();
        List<Trade> out = trades == null ? List.of() : trades;
        if (order.remaining() == 0) {
            refreshTopOfBook();
            return new SubmitResult(id, SubmitResult.Status.FILLED, null, out, filled, 0);
        }
        boolean rests = type == OrderType.LIMIT && tif == TimeInForce.GTC && order.isActive();
        if (rests) {
            rest(order);
            refreshTopOfBook();
            listener.onResting(order);
            return new SubmitResult(id, SubmitResult.Status.RESTING, null, out, filled, order.remaining());
        }
        order.deactivate();
        refreshTopOfBook();
        SubmitResult.Status s = filled > 0 ? SubmitResult.Status.PARTIALLY_FILLED : SubmitResult.Status.CANCELLED;
        return new SubmitResult(id, s, null, out, filled, 0);
    }

    /**
     * Sweep the crossable opposite levels. The trade list is created lazily and returned (null when
     * nothing traded), so a passive limit that rests without crossing allocates no collection.
     */
    private List<Trade> match(Order aggressor, TreeMap<Long, Level> opposite, List<Trade> trades) {
        while (aggressor.remaining() > 0 && !opposite.isEmpty()) {
            Map.Entry<Long, Level> bestEntry = opposite.firstEntry();
            long restingPrice = bestEntry.getKey();
            if (!crosses(aggressor, restingPrice)) {
                break; // best opposite price is not marketable for this order
            }
            Level level = bestEntry.getValue();
            trades = matchAtLevel(aggressor, level, restingPrice, trades);
            if (level.orders.isEmpty() || level.totalQty == 0) {
                opposite.remove(restingPrice);
            }
        }
        return trades;
    }

    private List<Trade> matchAtLevel(Order aggressor, Level level, long price, List<Trade> trades) {
        while (aggressor.remaining() > 0 && !level.orders.isEmpty()) {
            Order resting = level.orders.peekFirst();
            if (!resting.isActive()) {
                level.orders.pollFirst();                       // discard a lazily-cancelled order
                continue;
            }
            if (resting.participant().equals(aggressor.participant())) {
                // Self-trade prevention: cancel the resting maker rather than print a wash trade.
                level.orders.pollFirst();
                level.totalQty -= resting.remaining();
                byId.remove(resting.id());
                resting.deactivate();
                listener.onCancelled(resting);
                continue;
            }
            long qty = Math.min(aggressor.remaining(), resting.remaining());
            Trade t = new Trade(++tradeSeq, price, qty, resting.id(), aggressor.id(),
                    resting.participant(), aggressor.participant(), aggressor.side(), clock.getAsLong());
            if (trades == null) {
                trades = new ArrayList<>();                      // allocate only once a fill occurs
            }
            trades.add(t);
            totalTrades++;
            listener.onTrade(t);

            aggressor.reduce(qty);
            resting.reduce(qty);
            level.totalQty -= qty;
            if (resting.isFilled()) {
                level.orders.pollFirst();
                byId.remove(resting.id());
            }
        }
        return trades;
    }

    /** Recompute the cached best bid/ask from the books. O(log n), called once per mutation. */
    private void refreshTopOfBook() {
        cachedBestBid = bids.isEmpty() ? null : bids.firstKey();
        cachedBestAsk = asks.isEmpty() ? null : asks.firstKey();
    }

    /**
     * Marketable quantity actually <i>tradable</i> by {@code aggressor} across crossable opposite
     * levels (for the FOK all-or-nothing gate).
     *
     * <p>Excludes the aggressor's own resting orders: self-trade prevention <b>cancels</b> those
     * rather than trading against them (see {@link #matchAtLevel}). Counting them here would let a
     * FOK order pass the "fully fillable" check and then, during matching, have its own liquidity
     * cancelled out from under it — partially filling and cancelling the remainder, the exact partial
     * print FOK exists to prevent. So we subtract same-participant resting size level by level.
     */
    private long marketableQty(Order aggressor, TreeMap<Long, Level> opposite) {
        long available = 0;
        for (Map.Entry<Long, Level> e : opposite.entrySet()) {
            if (!crosses(aggressor, e.getKey())) {
                break;
            }
            Level level = e.getValue();
            long tradable = level.totalQty;
            for (Order o : level.orders) {
                if (o.isActive() && o.participant().equals(aggressor.participant())) {
                    tradable -= o.remaining();      // STP will cancel this, not trade it
                }
            }
            available += tradable;
            if (available >= aggressor.qty()) {
                return available;
            }
        }
        return available;
    }

    private static boolean crosses(Order aggressor, long restingPrice) {
        if (aggressor.type() == OrderType.MARKET) {
            return true;
        }
        return aggressor.side() == Side.BUY
                ? aggressor.priceTicks() >= restingPrice
                : aggressor.priceTicks() <= restingPrice;
    }

    private void rest(Order order) {
        TreeMap<Long, Level> side = order.side() == Side.BUY ? bids : asks;
        Level level = side.computeIfAbsent(order.priceTicks(), k -> new Level());
        level.orders.addLast(order);
        level.totalQty += order.remaining();
        byId.put(order.id(), order);
    }

    private SubmitResult reject(long id, String reason) {
        return new SubmitResult(id, SubmitResult.Status.REJECTED, reason, List.of(), 0, 0);
    }

    private static String validate(OrderType type, TimeInForce tif, boolean postOnly, long priceTicks, long qty) {
        if (qty <= 0) return "quantity must be positive";
        if (type == OrderType.LIMIT && priceTicks <= 0) return "limit order requires a positive price";
        if (type == OrderType.MARKET && postOnly) return "market order cannot be post-only";
        if (type == OrderType.MARKET && tif == TimeInForce.GTC) return "market order cannot be GTC";
        if (postOnly && type != OrderType.LIMIT) return "post-only requires a limit order";
        return null;
    }

    // ─────────────────────────────────────────────────────────────────────────────────────────────
    // Cancel / replace
    // ─────────────────────────────────────────────────────────────────────────────────────────────
    /** Cancel a resting order by id. Returns true if it was live and is now removed. */
    public boolean cancel(long orderId) {
        Order order = byId.remove(orderId);
        if (order == null || !order.isActive()) {
            return false;
        }
        TreeMap<Long, Level> side = order.side() == Side.BUY ? bids : asks;
        Level level = side.get(order.priceTicks());
        if (level != null) {
            level.totalQty -= order.remaining();
            if (level.totalQty <= 0) {
                side.remove(order.priceTicks());
            }
        }
        order.deactivate();
        refreshTopOfBook();
        listener.onCancelled(order);
        return true;
    }

    /**
     * Amend a resting order. A pure size <b>reduction</b> at the same price keeps time priority
     * (in place); any price change or size <b>increase</b> loses priority — the old order is
     * cancelled and a new one submitted at the back of its queue (the exchange-correct rule).
     * Returns the new/adjusted order id, or −1 if the order isn't resting.
     */
    public long replace(long orderId, long newPriceTicks, long newQty) {
        Order order = byId.get(orderId);
        if (order == null || !order.isActive()) {
            return -1;
        }
        boolean priceUnchanged = newPriceTicks == order.priceTicks();
        boolean reduction = newQty < order.remaining();
        if (priceUnchanged && reduction && newQty > 0) {
            TreeMap<Long, Level> side = order.side() == Side.BUY ? bids : asks;
            Level level = side.get(order.priceTicks());
            if (level != null) {
                level.totalQty -= (order.remaining() - newQty);
            }
            order.setRemaining(newQty);           // keeps its place in the FIFO queue
            return order.id();
        }
        cancel(orderId);
        SubmitResult r = submit(order.participant(), order.side(), order.type(), order.tif(),
                order.postOnly(), newPriceTicks, newQty);
        return r.orderId();
    }

    // ─────────────────────────────────────────────────────────────────────────────────────────────
    // Read side — L2 (aggregated) and L3 (order-by-order) market data + invariants
    // ─────────────────────────────────────────────────────────────────────────────────────────────
    public String instrument() { return instrument; }
    public Long bestBid() { return cachedBestBid; } // O(1): maintained on every mutation
    public Long bestAsk() { return cachedBestAsk; }
    public long orderCount() { return totalOrders; }
    public long tradeCount() { return totalTrades; }

    public Long spreadTicks() {
        Long b = bestBid(), a = bestAsk();
        return (b == null || a == null) ? null : a - b;
    }

    /** Total active resting quantity across both sides — for conservation checks. */
    public long restingQuantity() {
        long total = 0;
        for (Level l : bids.values()) total += l.totalQty;
        for (Level l : asks.values()) total += l.totalQty;
        return total;
    }

    /** L2: top {@code depth} levels per side as {@code [priceTicks, quantity, orderCount]} rows. */
    public List<long[]> l2(Side side, int depth) {
        TreeMap<Long, Level> book = side == Side.BUY ? bids : asks;
        List<long[]> rows = new ArrayList<>();
        for (Map.Entry<Long, Level> e : book.entrySet()) {
            if (rows.size() >= depth) break;
            if (e.getValue().totalQty > 0) {
                rows.add(new long[]{e.getKey(), e.getValue().totalQty, activeCount(e.getValue())});
            }
        }
        return rows;
    }

    /** L3: the resting orders on a side, best-price-first then FIFO — the order-by-order book. */
    public List<Order> l3(Side side, int maxOrders) {
        TreeMap<Long, Level> book = side == Side.BUY ? bids : asks;
        List<Order> out = new ArrayList<>();
        for (Level level : book.values()) {
            for (Order o : level.orders) {
                if (o.isActive() && o.remaining() > 0) {
                    out.add(o);
                    if (out.size() >= maxOrders) return out;
                }
            }
        }
        return out;
    }

    private static long activeCount(Level level) {
        long n = 0;
        for (Order o : level.orders) if (o.isActive() && o.remaining() > 0) n++;
        return n;
    }
}
