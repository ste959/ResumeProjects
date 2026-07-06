package com.bonddesk.oms.fixedincome;

import java.math.BigDecimal;

/**
 * One dealer's firm price back on an RFQ, for the client's side of the trade: the
 * executable clean price, its implied yield, the spread (bps) to the benchmark curve at
 * which it trades, the size offered, and whether it is the best execution.
 */
public record DealerQuote(
        String dealer,
        BigDecimal price,
        BigDecimal yieldPct,
        BigDecimal spreadBps,
        BigDecimal size,
        boolean best
) {
}
