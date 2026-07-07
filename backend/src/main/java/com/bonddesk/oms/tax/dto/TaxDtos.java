package com.bonddesk.oms.tax.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/** API view models for the tax engine. */
public final class TaxDtos {

    private TaxDtos() {
    }

    public record TaxTrade(Instant time, String side, double quantity, double price) {
    }

    /**
     * A tax computation request. {@code lotMethod} ∈ FIFO|LIFO|HIFO; {@code regime} ∈
     * RETAIL (capital gains + wash sales for securities) | TRADER_MTM (§475(f) mark-to-market:
     * all ordinary, no wash sales, no long-term). {@code assetClass} ∈ CRYPTO|EQUITY — crypto
     * is property, so the wash-sale rule does not apply to it.
     */
    public record TaxRequest(
            String assetClass,
            String lotMethod,
            String regime,
            Double ordinaryRate,
            Double longTermRate,
            Double markPrice,       // period-end mark for §475(f) MTM (defaults to last trade)
            List<TaxTrade> trades
    ) {
    }

    /**
     * One realized disposal: which lot, gain/loss, holding period, and any wash-sale disallowance.
     * Reported dollar figures ({@code proceeds}, {@code costBasis}, {@code gain}, {@code washDisallowed})
     * are {@link BigDecimal} at scale 2 so they are exact to the cent; {@code quantity} stays a
     * double as it is a share/coin count, not money.
     */
    public record Disposition(
            Instant acquired,
            Instant sold,
            double quantity,
            BigDecimal proceeds,
            BigDecimal costBasis,
            BigDecimal gain,
            long holdingDays,
            boolean longTerm,
            BigDecimal washDisallowed
    ) {
    }

    /**
     * Tax report. All reported dollar figures are {@link BigDecimal} at scale 2 (cent-exact);
     * {@code effectiveTaxRate} is a ratio and {@code openPosition}/{@code openAvgBasis} are a
     * quantity and a per-unit basis, so those stay doubles.
     */
    public record TaxReport(
            String assetClass,
            String regime,
            String lotMethod,
            BigDecimal proceeds,
            BigDecimal realizedGain,
            BigDecimal shortTermGain,
            BigDecimal longTermGain,
            BigDecimal washSaleDisallowed,
            BigDecimal unrealizedMtm,
            BigDecimal taxableGain,
            BigDecimal taxOwed,
            BigDecimal preTaxPnl,
            BigDecimal afterTaxPnl,
            double effectiveTaxRate,
            double openPosition,
            double openAvgBasis,
            List<Disposition> dispositions
    ) {
    }
}
