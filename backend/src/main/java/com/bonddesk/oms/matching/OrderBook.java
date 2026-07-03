package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * A central limit order book for a single instrument, matching on strict
 * <b>price-time priority</b>:
 * <ul>
 *   <li><b>Price</b> — an aggressor always trades against the best available opposite
 *       price first (highest bid / lowest ask).</li>
 *   <li><b>Time</b> — within a price level, the earliest-resting order fills first (FIFO).</li>
 * </ul>
 *
 * <p>Price levels are held in {@link TreeMap}s so the best price is O(1) to read and any
 * level is O(log n) to find; each level is a FIFO {@link ArrayDeque}. Cancellation is
 * lazy — the order is flagged inactive and skipped (then discarded) during matching —
 * giving O(1) cancels while keeping the queues contiguous.
 *
 * <p>Not thread-safe by design: the engine is a single-threaded core. Concurrency is
 * handled one level up (a lock per book) so the matching path stays allocation-light and
 * branch-predictable.
 */
public final class OrderBook {

    /** One price level: a FIFO queue plus the running active quantity at that price. */
    private static final class Level {
        final Deque<BookOrder> orders = new ArrayDeque<>();
        long totalQty;
    }

    private final String instrument;
    // Bids: highest price first. Asks: lowest price first.
    private final TreeMap<Long, Level> bids = new TreeMap<>(Comparator.reverseOrder());
    private final TreeMap<Long, Level> asks = new TreeMap<>();
    private final Map<Long, BookOrder> byId = new HashMap<>();

    private long tradeSequence;

    public OrderBook(String instrument) {
        this.instrument = instrument;
    }

    public String instrument() {
        return instrument;
    }

    /**
     * Submit an order: match its marketable quantity against the opposite side, then rest
     * any remainder (LIMIT only; MARKET remainder is cancelled). Returns the trades
     * generated, in execution order.
     */
    public List<Trade> submit(BookOrder incoming) {
        List<Trade> trades = new ArrayList<>();
        TreeMap<Long, Level> opposite = incoming.side() == OrderSide.BUY ? asks : bids;

        while (incoming.remaining() > 0 && !opposite.isEmpty()) {
            Map.Entry<Long, Level> bestEntry = opposite.firstEntry();
            long restingPrice = bestEntry.getKey();
            if (!crosses(incoming, restingPrice)) {
                break; // best opposite price is not marketable for this order
            }
            Level level = bestEntry.getValue();
            matchAtLevel(incoming, level, restingPrice, trades);
            if (level.orders.isEmpty() || level.totalQty == 0) {
                opposite.remove(restingPrice);
            }
        }

        if (incoming.remaining() > 0) {
            if (incoming.type() == OrderType.LIMIT) {
                rest(incoming);
            } else {
                incoming.deactivate(); // an unfilled MARKET remainder does not rest — it dies
            }
        }
        return trades;
    }

    private void matchAtLevel(BookOrder incoming, Level level, long price, List<Trade> trades) {
        while (incoming.remaining() > 0 && !level.orders.isEmpty()) {
            BookOrder resting = level.orders.peekFirst();
            if (!resting.isActive()) {
                level.orders.pollFirst(); // discard a lazily-cancelled order
                continue;
            }
            long qty = Math.min(incoming.remaining(), resting.remaining());
            trades.add(makeTrade(incoming, resting, price, qty));

            incoming.reduce(qty);
            resting.reduce(qty);
            level.totalQty -= qty;

            if (resting.isFilled()) {
                level.orders.pollFirst();
                byId.remove(resting.id());
            }
        }
    }

    /** True if {@code incoming} is willing to trade at {@code restingPrice}. */
    private static boolean crosses(BookOrder incoming, long restingPrice) {
        if (incoming.type() == OrderType.MARKET) {
            return true;
        }
        return incoming.side() == OrderSide.BUY
                ? incoming.priceTicks() >= restingPrice
                : incoming.priceTicks() <= restingPrice;
    }

    private Trade makeTrade(BookOrder aggressor, BookOrder resting, long price, long qty) {
        boolean aggressorBuys = aggressor.side() == OrderSide.BUY;
        String buyRef = aggressorBuys ? aggressor.ownerRef() : resting.ownerRef();
        String sellRef = aggressorBuys ? resting.ownerRef() : aggressor.ownerRef();
        return new Trade(aggressor.id(), resting.id(), buyRef, sellRef, price, qty, ++tradeSequence);
    }

    private void rest(BookOrder order) {
        TreeMap<Long, Level> side = order.side() == OrderSide.BUY ? bids : asks;
        Level level = side.computeIfAbsent(order.priceTicks(), k -> new Level());
        level.orders.addLast(order);
        level.totalQty += order.remaining();
        byId.put(order.id(), order);
    }

    /** Cancel a resting order by id. Returns true if it was live and is now removed. */
    public boolean cancel(long orderId) {
        BookOrder order = byId.remove(orderId);
        if (order == null || !order.isActive()) {
            return false;
        }
        TreeMap<Long, Level> side = order.side() == OrderSide.BUY ? bids : asks;
        Level level = side.get(order.priceTicks());
        if (level != null) {
            level.totalQty -= order.remaining();
            if (level.totalQty <= 0) {
                side.remove(order.priceTicks()); // no active quantity left at this price
            }
        }
        order.deactivate(); // physically removed from its queue lazily during matching
        return true;
    }

    // ---- Read-side accessors (for display and invariant checks) ----

    public Long bestBid() {
        return bids.isEmpty() ? null : bids.firstKey();
    }

    public Long bestAsk() {
        return asks.isEmpty() ? null : asks.firstKey();
    }

    /** Spread in ticks, or null if either side is empty. */
    public Long spreadTicks() {
        Long bid = bestBid();
        Long ask = bestAsk();
        return (bid == null || ask == null) ? null : ask - bid;
    }

    /** Total active resting quantity across both sides — used by conservation checks. */
    public long restingQuantity() {
        long total = 0;
        for (Level l : bids.values()) total += l.totalQty;
        for (Level l : asks.values()) total += l.totalQty;
        return total;
    }

    /** Top {@code depth} levels per side as {@code [priceTicks, quantity]} rows. */
    public List<long[]> depth(OrderSide side, int depth) {
        TreeMap<Long, Level> book = side == OrderSide.BUY ? bids : asks;
        List<long[]> rows = new ArrayList<>();
        for (Map.Entry<Long, Level> e : book.entrySet()) {
            if (rows.size() >= depth) break;
            if (e.getValue().totalQty > 0) {
                rows.add(new long[]{e.getKey(), e.getValue().totalQty});
            }
        }
        return Collections.unmodifiableList(rows);
    }
}
