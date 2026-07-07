package com.bonddesk.oms.rates;

import java.util.List;

/** Wire models for the live rates desk: the market-data snapshot pushed over WebSocket + order entry. */
public final class RatesDtos {

    private RatesDtos() {}

    public record Snapshot(long tick, CurveView curve, RfqView lastRfq, List<DealerView> dealers,
                           BookView book, AnalyticsView analytics) {}

    public record CurveView(String asOf, double[] tenors, double[] parYields, double[] zeroRates,
                            double parallelShockBps, double slopeShockBps) {}

    public record RfqView(String instrument, String side, double sizeMM, int nDealers, double compositeMid,
                          double leakagePx, double executedPrice, String winner, boolean weWon,
                          double costBps, double competitionPx, List<QuoteView> quotes) {}

    public record QuoteView(String name, double price, double fromMidBps, boolean best, boolean us) {}

    public record DealerView(String name, double inventory, boolean us) {}

    public record BookView(double valueUsd, double dv01Usd, List<KrView> keyRateDv01,
                           List<PositionView> positions, PnlAttribution pnl) {}

    public record KrView(double tenor, double dv01Usd) {}

    public record PositionView(String instrument, double positionMM, double price, double dv01Usd) {}

    /** Cumulative desk P&L split into its drivers (all $). total = trading + carry + rates + credit. */
    public record PnlAttribution(double totalUsd, double trading, double carry,
                                 double rateParallel, double rateReshape, double credit) {}

    public record AnalyticsView(double winRatePct, long ourWins, long totalRfqs, double avgCostBps,
                                List<LeakagePoint> leakageCurve, List<CostBySize> costBySize) {}

    /** The competition-vs-leakage trade-off: leakage cost by how many dealers were shopped. */
    public record LeakagePoint(int dealers, double avgLeakagePx, double avgCostBps, long count) {}

    public record CostBySize(String bucket, double avgCostBps, long count) {}

    public record SubmitRfqRequest(String instrument, String side, Double sizeMM, Integer nDealers) {}

    public record ShockRequest(double parallelBps, double slopeBps) {}
}
