package com.bonddesk.rates;

import java.util.List;

/**
 * The outcome of one request-for-quote auction: every dealer's price, the best-execution winner, and
 * the transaction-cost breakdown — cost vs. the composite mid, the competition benefit (how much the
 * auction beat the second-best), and the <b>leakage</b> (how far the reference moved against the
 * client just by shopping the order to more dealers).
 */
public record RfqAuction(
        String instrument,
        boolean clientBuys,
        double sizeMM,
        double compositeMid,      // fair mid off the curve, no leakage
        double leakagePx,         // how far the effective mid moved against the client
        List<Quote> quotes,
        int winnerIndex,
        double executedPrice,
        double costPx,            // client's cost vs composite mid (price points, + = paid the spread)
        double costBps,           // same, in bps of yield (costPx / DV01)
        double competitionPx      // executed vs 2nd-best — the value of the auction
) {
    /** One dealer's quote. {@code fromMidBps} is the quoted level's distance from the composite mid, in bps. */
    public record Quote(int dealer, String name, double price, double fromMidBps, boolean best) {}

    public Quote winner() {
        return quotes.get(winnerIndex);
    }
}
