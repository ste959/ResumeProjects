package com.bonddesk.oms.market;

import com.bonddesk.oms.market.LiveOrderBook.Level;
import com.bonddesk.oms.market.dto.MarketDtos.BookView;
import com.bonddesk.oms.market.dto.MarketDtos.CryptoPositionView;
import com.bonddesk.oms.market.dto.MarketDtos.DepthLevel;
import com.bonddesk.oms.market.dto.MarketDtos.PaperOrder;
import com.bonddesk.oms.market.dto.MarketDtos.PaperOrderRequest;
import com.bonddesk.oms.market.dto.MarketDtos.ProductQuote;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

/** Live crypto market data (real Coinbase feed) and paper trading against the real book. */
@RestController
@RequestMapping("/api/market")
@Tag(name = "Live Market", description = "Real Coinbase order book + paper trading against live liquidity")
public class MarketController {

    private static final BigDecimal BPS = BigDecimal.valueOf(10_000);

    private final MarketDataService marketData;
    private final PaperTradingService paper;

    public MarketController(MarketDataService marketData, PaperTradingService paper) {
        this.marketData = marketData;
        this.paper = paper;
    }

    @GetMapping("/products")
    @Operation(summary = "Subscribed products with live top-of-book quotes")
    public List<ProductQuote> products() {
        return marketData.products().stream().map(this::quote).toList();
    }

    @GetMapping("/{product}/book")
    @Operation(summary = "Live depth ladder for a product")
    public BookView book(@PathVariable String product, @RequestParam(defaultValue = "15") int depth) {
        LiveOrderBook book = marketData.book(product);
        return new BookView(product, quote(product),
                ladder(book.depth(true, depth)), ladder(book.depth(false, depth)));
    }

    @GetMapping("/{product}/trades")
    @Operation(summary = "Recent real trades (the tape)")
    public List<TradePrint> trades(@PathVariable String product) {
        return marketData.recentTrades(product);
    }

    @PostMapping("/{product}/orders")
    @Operation(summary = "Paper-trade an order against the live book (VWAP + real slippage)")
    public PaperOrder submit(@PathVariable String product, @RequestBody PaperOrderRequest request) {
        return paper.submit(product, request);
    }

    @GetMapping("/orders")
    @Operation(summary = "Recent paper orders (the crypto blotter)")
    public List<PaperOrder> orders() {
        return paper.recentOrders();
    }

    @GetMapping("/positions")
    @Operation(summary = "Crypto positions with live mark-to-market")
    public List<CryptoPositionView> positions() {
        return paper.positions();
    }

    // ---- helpers ----

    private ProductQuote quote(String product) {
        LiveOrderBook book = marketData.book(product);
        BigDecimal bid = book.bestBid();
        BigDecimal ask = book.bestAsk();
        BigDecimal mid = book.mid();
        BigDecimal spread = (bid == null || ask == null) ? null : ask.subtract(bid);
        BigDecimal spreadBps = (spread == null || mid == null || mid.signum() == 0) ? null
                : spread.divide(mid, 8, RoundingMode.HALF_UP).multiply(BPS).setScale(2, RoundingMode.HALF_UP);
        return new ProductQuote(product, bid, ask, mid, spread, spreadBps, marketData.lastPrice(product));
    }

    /** Attach a running cumulative size to depth levels. */
    private List<DepthLevel> ladder(List<Level> levels) {
        List<DepthLevel> rows = new ArrayList<>(levels.size());
        BigDecimal cumulative = BigDecimal.ZERO;
        for (Level l : levels) {
            cumulative = cumulative.add(l.size());
            rows.add(new DepthLevel(l.price(), l.size(), cumulative));
        }
        return rows;
    }
}
