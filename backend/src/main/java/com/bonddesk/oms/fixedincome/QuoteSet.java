package com.bonddesk.oms.fixedincome;

import java.math.BigDecimal;
import java.util.List;

/**
 * The full pricing context for an RFQ: the benchmark curve yield at the bond's tenor, the
 * credit spread added for its rating, the resulting fair yield/price, and the dealers'
 * firm quotes around that fair value.
 */
public record QuoteSet(
        BigDecimal tenorYears,
        BigDecimal curveYieldPct,
        BigDecimal creditSpreadBps,
        BigDecimal fairYieldPct,
        BigDecimal fairClean,
        List<DealerQuote> quotes
) {
}
