package com.bonddesk.oms.market.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/** Small read/write models for the live crypto market surface. */
public final class MarketDtos {

    private MarketDtos() {
    }

    /** Top-of-book snapshot for a product. */
    public record ProductQuote(
            String product,
            BigDecimal bestBid,
            BigDecimal bestAsk,
            BigDecimal mid,
            BigDecimal spread,
            BigDecimal spreadBps,
            BigDecimal lastPrice
    ) {}

    /** One depth ladder row with running cumulative size. */
    public record DepthLevel(BigDecimal price, BigDecimal size, BigDecimal cumulative) {}

    public record BookView(String product, ProductQuote quote,
                           List<DepthLevel> bids, List<DepthLevel> asks) {}

    /** Paper order submitted by the desk against the live book. */
    public record PaperOrderRequest(String side, String type, BigDecimal size, BigDecimal limitPrice) {}

    public record PaperFill(BigDecimal price, BigDecimal size) {}

    public record PaperOrder(
            String id,
            String product,
            String side,
            String type,
            BigDecimal requestedSize,
            BigDecimal limitPrice,
            String status,
            BigDecimal filledSize,
            BigDecimal avgPrice,
            BigDecimal notional,
            BigDecimal slippageBps,
            Instant createdAt,
            List<PaperFill> fills
    ) {}

    public record CryptoPositionView(
            String product,
            BigDecimal netSize,
            BigDecimal avgCost,
            BigDecimal markPrice,
            BigDecimal marketValue,
            BigDecimal unrealizedPnl
    ) {}
}
