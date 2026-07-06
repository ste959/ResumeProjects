package com.bonddesk.oms.tax.dto;

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

    /** One realized disposal: which lot, gain/loss, holding period, and any wash-sale disallowance. */
    public record Disposition(
            Instant acquired,
            Instant sold,
            double quantity,
            double proceeds,
            double costBasis,
            double gain,
            long holdingDays,
            boolean longTerm,
            double washDisallowed
    ) {
    }

    public record TaxReport(
            String assetClass,
            String regime,
            String lotMethod,
            double proceeds,
            double realizedGain,
            double shortTermGain,
            double longTermGain,
            double washSaleDisallowed,
            double unrealizedMtm,
            double taxableGain,
            double taxOwed,
            double preTaxPnl,
            double afterTaxPnl,
            double effectiveTaxRate,
            double openPosition,
            double openAvgBasis,
            List<Disposition> dispositions
    ) {
    }
}
