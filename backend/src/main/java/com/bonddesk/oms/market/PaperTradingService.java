package com.bonddesk.oms.market;

import com.bonddesk.oms.market.LiveOrderBook.Level;
import com.bonddesk.oms.market.dto.MarketDtos.CryptoPositionView;
import com.bonddesk.oms.market.dto.MarketDtos.PaperFill;
import com.bonddesk.oms.market.dto.MarketDtos.PaperOrder;
import com.bonddesk.oms.market.dto.MarketDtos.PaperOrderRequest;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Paper trading against the <b>live</b> Coinbase book: a desk order sweeps the real
 * resting liquidity, filling level-by-level and paying genuine multi-level slippage
 * versus the arrival mid — no simulated market-maker. Positions and orders are kept
 * in memory (this is a live-market sandbox, not the persisted FI OMS).
 */
@Service
public class PaperTradingService {

    private static final BigDecimal BPS = BigDecimal.valueOf(10_000);
    private static final int MAX_ORDERS = 100;

    private final MarketDataService marketData;
    private final Clock clock;

    private final Map<String, Position> positions = new ConcurrentHashMap<>();
    private final Deque<PaperOrder> orders = new ArrayDeque<>();

    public PaperTradingService(MarketDataService marketData, Clock clock) {
        this.marketData = marketData;
        this.clock = clock;
    }

    /** Signed running position for one product. */
    private static final class Position {
        BigDecimal net = BigDecimal.ZERO;
        BigDecimal avgCost = BigDecimal.ZERO;
    }

    public synchronized PaperOrder submit(String product, PaperOrderRequest req) {
        boolean buy = "BUY".equalsIgnoreCase(req.side());
        LiveOrderBook book = marketData.book(product);
        BigDecimal arrivalMid = book.mid();

        // Buyers lift asks (lowest first); sellers hit bids (highest first) — the book
        // returns each side best-first already.
        List<Level> levels = book.snapshot(!buy);

        BigDecimal remaining = req.size();
        BigDecimal filled = BigDecimal.ZERO;
        BigDecimal cash = BigDecimal.ZERO; // notional traded
        List<PaperFill> fills = new ArrayList<>();

        for (Level level : levels) {
            if (remaining.signum() <= 0) break;
            if (!marketable(buy, req, level.price())) break; // limit price no longer satisfied
            BigDecimal take = remaining.min(level.size());
            fills.add(new PaperFill(level.price(), take));
            cash = cash.add(level.price().multiply(take));
            filled = filled.add(take);
            remaining = remaining.subtract(take);
        }

        BigDecimal avgPrice = filled.signum() > 0
                ? cash.divide(filled, 8, RoundingMode.HALF_UP) : null;
        BigDecimal slippage = slippageBps(buy, avgPrice, arrivalMid);

        if (filled.signum() > 0) {
            applyToPosition(product, buy, filled, avgPrice);
        }

        PaperOrder order = new PaperOrder(
                UUID.randomUUID().toString(), product, buy ? "BUY" : "SELL", req.type().toUpperCase(),
                req.size(), req.limitPrice(),
                statusFor(filled, req.size()),
                filled, avgPrice,
                cash.setScale(2, RoundingMode.HALF_UP),
                slippage, clock.instant(), fills);

        synchronized (orders) {
            orders.addFirst(order);
            while (orders.size() > MAX_ORDERS) orders.removeLast();
        }
        return order;
    }

    private boolean marketable(boolean buy, PaperOrderRequest req, BigDecimal levelPrice) {
        if (!"LIMIT".equalsIgnoreCase(req.type()) || req.limitPrice() == null) {
            return true; // market order takes any price
        }
        return buy ? levelPrice.compareTo(req.limitPrice()) <= 0
                : levelPrice.compareTo(req.limitPrice()) >= 0;
    }

    private static String statusFor(BigDecimal filled, BigDecimal requested) {
        if (filled.signum() == 0) return "UNFILLED";
        return filled.compareTo(requested) >= 0 ? "FILLED" : "PARTIALLY_FILLED";
    }

    private BigDecimal slippageBps(boolean buy, BigDecimal avgPrice, BigDecimal arrivalMid) {
        if (avgPrice == null || arrivalMid == null || arrivalMid.signum() == 0) {
            return BigDecimal.ZERO;
        }
        BigDecimal dev = buy ? avgPrice.subtract(arrivalMid) : arrivalMid.subtract(avgPrice);
        return dev.divide(arrivalMid, 8, RoundingMode.HALF_UP).multiply(BPS).setScale(2, RoundingMode.HALF_UP);
    }

    private void applyToPosition(String product, boolean buy, BigDecimal size, BigDecimal price) {
        Position pos = positions.computeIfAbsent(product, k -> new Position());
        BigDecimal signed = buy ? size : size.negate();
        BigDecimal newNet = pos.net.add(signed);
        if (pos.net.signum() == 0) {
            pos.avgCost = price;
        } else if (pos.net.signum() == signed.signum()) {
            BigDecimal oldAbs = pos.net.abs();
            BigDecimal addAbs = size;
            pos.avgCost = oldAbs.multiply(pos.avgCost).add(addAbs.multiply(price))
                    .divide(oldAbs.add(addAbs), 8, RoundingMode.HALF_UP);
        } else if (newNet.signum() == 0) {
            pos.avgCost = BigDecimal.ZERO;
        } else if (pos.net.signum() != newNet.signum()) {
            pos.avgCost = price; // flipped through zero
        } // else reducing: avg cost unchanged
        pos.net = newNet;
    }

    public List<PaperOrder> recentOrders() {
        synchronized (orders) {
            return new ArrayList<>(orders);
        }
    }

    public List<CryptoPositionView> positions() {
        List<CryptoPositionView> views = new ArrayList<>();
        positions.forEach((product, pos) -> {
            if (pos.net.signum() == 0) return;
            BigDecimal mark = marketData.book(product).mid();
            BigDecimal marketValue = mark == null ? null
                    : pos.net.multiply(mark).setScale(2, RoundingMode.HALF_UP);
            BigDecimal pnl = mark == null ? null
                    : pos.net.multiply(mark.subtract(pos.avgCost)).setScale(2, RoundingMode.HALF_UP);
            views.add(new CryptoPositionView(product, pos.net, pos.avgCost.setScale(2, RoundingMode.HALF_UP),
                    mark, marketValue, pnl));
        });
        views.sort(Comparator.comparing(CryptoPositionView::product));
        return views;
    }
}
