package com.bonddesk.oms.exchange;

import java.util.List;

/** Wire models for the live exchange: the market-data snapshot pushed over WebSocket, plus order entry. */
public final class ExchangeDtos {

    private ExchangeDtos() {}

    /** One market-data frame: the book (L2 + best-level L3 queues), recent trades, and engine stats. */
    public record Snapshot(
            String instrument,
            double tickSize,
            double lotSize,
            long tick,
            Stats stats,
            List<Level> bids,
            List<Level> asks,
            List<QueueOrder> bidQueue,
            List<QueueOrder> askQueue,
            List<TradeView> trades
    ) {}

    /** An aggregated L2 price level (with how many orders queue there, and whether the maker/you are on it). */
    public record Level(double price, double size, int orders, boolean mm, boolean you) {}

    /** An individual resting order at the top of book (L3) — for the price-time-priority queue view. */
    public record QueueOrder(long id, double price, double size, String owner) {}

    public record Stats(
            double fair, double mid, Double spreadBps,
            long mmInventoryLots, double mmInventory, double mmPnl, long mmFills,
            double ordersPerSec, long tradeCount, long peakOrdersPerSec,
            long p50LatencyNs, long p99LatencyNs, double restingSize
    ) {}

    public record TradeView(long seq, double price, double size, String aggressor, String maker, String taker) {}

    public record PlaceRequest(String side, String type, String tif, boolean postOnly, Double price, Double size) {}

    public record PlaceResponse(long orderId, String status, String reason, int trades,
                                double filledSize, double restingSize) {}

    // ── market-maker analytics ──────────────────────────────────────────────────────────────────
    public record AnalyticsView(PnlAttribution pnl, LatencyReport latency, List<FillView> fills, Summary summary) {}

    /** Maker P&L split: spread captured (+), adverse selection (−), and the open-inventory residual. */
    public record PnlAttribution(double totalUsd, double spreadCapturedUsd, double adverseSelectionUsd,
                                 double inventoryUsd, long markedOutFills) {}

    public record LatencyReport(long p50Ns, long p99Ns, long maxNs, List<LatencyBucket> byMatchDepth, String note) {}

    /** Latency grouped by how many resting orders the submit matched — where the spikes come from. */
    public record LatencyBucket(String depth, long p50Ns, long p99Ns, long count) {}

    /** One maker fill for the sortable log. {@code markoutBps} is null until the fill matures. */
    public record FillView(long seq, long tick, String side, double price, double size, String aggressor,
                           double spreadBps, double inventory, double edgeBps, Double markoutBps) {}

    public record Summary(long fills, long adverseFills, double informedShare,
                          double avgEdgeBps, double avgMarkoutBps) {}
}
