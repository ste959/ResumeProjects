package com.bonddesk.oms.market.stream;

import com.bonddesk.oms.market.TradePrint;
import com.bonddesk.oms.market.dto.MarketDtos.DepthLevel;
import com.bonddesk.oms.market.dto.MarketDtos.ProductQuote;

import java.util.List;

/**
 * The JSON frames pushed over the live market-data WebSocket ({@code /ws/market}). Every frame
 * carries a {@code type} discriminator so the browser can route it. Three kinds:
 *
 * <ul>
 *   <li>{@code book} — a depth-ladder snapshot (top-of-book quote + N levels each side), sent every tick;</li>
 *   <li>{@code trade} — the new trade prints since the client's cursor (the order-flow tape);</li>
 *   <li>{@code metrics} — live microstructure + execution metrics for the strip.</li>
 * </ul>
 */
public final class StreamFrames {

    private StreamFrames() {}

    public record BookFrame(String type, String product, ProductQuote quote,
                            List<DepthLevel> bids, List<DepthLevel> asks) {
        public BookFrame(String product, ProductQuote quote, List<DepthLevel> bids, List<DepthLevel> asks) {
            this("book", product, quote, bids, asks);
        }
    }

    public record TradeFrame(String type, String product, List<TradePrint> trades) {
        public TradeFrame(String product, List<TradePrint> trades) {
            this("trade", product, trades);
        }
    }

    /** Live market-making / microstructure metrics for the strip. All doubles are display-ready. */
    public record Metrics(boolean ready, double mid, double microprice, double imbalance,
                          double spreadBps, double microPremiumBps, double bookUpdatesPerSec,
                          double tradesPerSec, long bookAgeMs, double fillRatePct,
                          double avgSlippageBps, int paperOrders) {}

    public record MetricsFrame(String type, String product, Metrics metrics) {
        public MetricsFrame(String product, Metrics metrics) {
            this("metrics", product, metrics);
        }
    }
}
