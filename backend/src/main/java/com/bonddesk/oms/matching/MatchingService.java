package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Runs one {@link OrderBook} per instrument and bridges it to the OMS. Desk orders are
 * submitted to their instrument's book when routed; the liquidity provider posts the
 * other side. Each book is a single-threaded core, so access is serialised on the book
 * instance — the engine itself never needs internal locking.
 *
 * <p>Fills are emitted as {@link DeskFillEvent}s rather than by calling the order service
 * directly, keeping the engine free of any persistence dependency.
 */
@Service
@ConditionalOnProperty(prefix = "oms.matching", name = "enabled", havingValue = "true")
public class MatchingService implements MatchingGateway {

    private static final String VENUE = "CLOB";

    private final Map<String, OrderBook> books = new ConcurrentHashMap<>();
    private final Map<String, Long> deskRefToEngineId = new ConcurrentHashMap<>();
    private final AtomicLong idSeq = new AtomicLong();
    private final ApplicationEventPublisher events;

    public MatchingService(ApplicationEventPublisher events) {
        this.events = events;
    }

    private OrderBook bookFor(String cusip) {
        return books.computeIfAbsent(cusip, OrderBook::new);
    }

    @Override
    public void route(Order order) {
        String cusip = order.getSecurity().getCusip();
        OrderBook book = bookFor(cusip);
        long id = idSeq.incrementAndGet();
        long priceTicks = order.getOrderType() == OrderType.LIMIT
                ? Ticks.priceToTicks(order.getLimitPrice()) : 0L;
        long qty = Ticks.qtyToLong(order.remainingQuantity());
        if (qty <= 0) {
            return;
        }
        BookOrder bo = new BookOrder(id, order.getSide(), order.getOrderType(), priceTicks, qty, order.getOrderRef());

        // Match under the book lock (the engine's single-threaded core), but publish/persist the
        // resulting fills only AFTER releasing it. Fill publishing runs FillRecorder ->
        // OrderService.recordFill, a @Transactional DB write; holding the matching lock across
        // that would let a slow DB stall every other order on this instrument.
        List<Trade> trades;
        synchronized (book) {
            trades = book.submit(bo);
            if (bo.isActive() && bo.remaining() > 0) {
                deskRefToEngineId.put(order.getOrderRef(), id); // rests — remember it for cancels
            }
        }
        publishFills(trades);
    }

    @Override
    public void cancel(Order order) {
        Long id = deskRefToEngineId.remove(order.getOrderRef());
        if (id == null) {
            return;
        }
        OrderBook book = bookFor(order.getSecurity().getCusip());
        synchronized (book) {
            book.cancel(id);
        }
    }

    /** Post a resting liquidity order (the market-maker side). Returns its engine id. */
    public long postLiquidity(String cusip, OrderSide side, long priceTicks, long qty) {
        OrderBook book = bookFor(cusip);
        long id = idSeq.incrementAndGet();
        BookOrder bo = new BookOrder(id, side, OrderType.LIMIT, priceTicks, qty, null);
        List<Trade> trades;
        synchronized (book) {
            trades = book.submit(bo);
        }
        publishFills(trades); // persist/publish outside the matching lock (see route())
        return id;
    }

    public void cancelLiquidity(String cusip, long engineId) {
        OrderBook book = bookFor(cusip);
        synchronized (book) {
            book.cancel(engineId);
        }
    }

    /** Best bid/ask in price terms, for display; either may be null. */
    public BigDecimal[] topOfBook(String cusip) {
        OrderBook book = bookFor(cusip);
        synchronized (book) {
            Long bid = book.bestBid();
            Long ask = book.bestAsk();
            return new BigDecimal[]{
                    bid == null ? null : Ticks.ticksToPrice(bid),
                    ask == null ? null : Ticks.ticksToPrice(ask)
            };
        }
    }

    private void publishFills(List<Trade> trades) {
        for (Trade t : trades) {
            BigDecimal price = Ticks.ticksToPrice(t.priceTicks());
            BigDecimal qty = Ticks.longToQty(t.quantity());
            if (t.buyRef() != null) {
                events.publishEvent(new DeskFillEvent(t.buyRef(), qty, price, VENUE));
            }
            if (t.sellRef() != null) {
                events.publishEvent(new DeskFillEvent(t.sellRef(), qty, price, VENUE));
            }
        }
    }
}
