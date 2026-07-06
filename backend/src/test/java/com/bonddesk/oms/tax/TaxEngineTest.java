package com.bonddesk.oms.tax;

import com.bonddesk.oms.tax.dto.TaxDtos.TaxReport;
import com.bonddesk.oms.tax.dto.TaxDtos.TaxRequest;
import com.bonddesk.oms.tax.dto.TaxDtos.TaxTrade;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

class TaxEngineTest {

    private final TaxEngine engine = new TaxEngine();

    private static TaxTrade trade(String time, String side, double qty, double price) {
        return new TaxTrade(Instant.parse(time), side, qty, price);
    }

    @Test
    void lotMethodChangesTheRealizedGain() {
        // Buy at 100 then 110, sell one at 120. FIFO sells the 100 lot; HIFO sells the 110 lot.
        List<TaxTrade> trades = List.of(
                trade("2026-01-01T00:00:00Z", "BUY", 1, 100),
                trade("2026-01-02T00:00:00Z", "BUY", 1, 110),
                trade("2026-01-03T00:00:00Z", "SELL", 1, 120));

        TaxReport fifo = engine.compute(new TaxRequest("CRYPTO", "FIFO", "RETAIL", null, null, null, trades));
        TaxReport hifo = engine.compute(new TaxRequest("CRYPTO", "HIFO", "RETAIL", null, null, null, trades));

        assertThat(fifo.realizedGain()).isEqualTo(20.0);
        assertThat(hifo.realizedGain()).isEqualTo(10.0); // HIFO minimises the gain
    }

    @Test
    void shortTermIsTaxedHigherThanLongTerm() {
        List<TaxTrade> longTerm = List.of(
                trade("2024-01-01T00:00:00Z", "BUY", 1, 100),
                trade("2026-01-01T00:00:00Z", "SELL", 1, 120)); // held ~2 years
        List<TaxTrade> shortTerm = List.of(
                trade("2026-01-01T00:00:00Z", "BUY", 1, 100),
                trade("2026-01-15T00:00:00Z", "SELL", 1, 120)); // held 14 days

        TaxReport lt = engine.compute(new TaxRequest("CRYPTO", "FIFO", "RETAIL", 0.37, 0.20, null, longTerm));
        TaxReport st = engine.compute(new TaxRequest("CRYPTO", "FIFO", "RETAIL", 0.37, 0.20, null, shortTerm));

        assertThat(lt.longTermGain()).isEqualTo(20.0);
        assertThat(lt.taxOwed()).isEqualTo(4.0);          // 20 * 20%
        assertThat(st.shortTermGain()).isEqualTo(20.0);
        assertThat(st.taxOwed()).isCloseTo(7.4, within(1e-6)); // 20 * 37% — turnover has a tax cost
    }

    @Test
    void washSaleDisallowsTheLossForEquitiesButNotCrypto() {
        // Sell at a loss, then rebuy the same name within 30 days.
        List<TaxTrade> trades = List.of(
                trade("2026-01-01T00:00:00Z", "BUY", 1, 100),
                trade("2026-06-01T00:00:00Z", "SELL", 1, 90),   // -10 loss
                trade("2026-06-10T00:00:00Z", "BUY", 1, 95));   // replacement within 30 days

        TaxReport equity = engine.compute(new TaxRequest("EQUITY", "FIFO", "RETAIL", null, null, null, trades));
        TaxReport crypto = engine.compute(new TaxRequest("CRYPTO", "FIFO", "RETAIL", null, null, null, trades));

        assertThat(equity.washSaleDisallowed()).isEqualTo(10.0); // loss disallowed
        assertThat(equity.taxableGain()).isEqualTo(0.0);         // -10 realized + 10 added back
        assertThat(crypto.washSaleDisallowed()).isEqualTo(0.0);  // crypto is property — rule N/A
        assertThat(crypto.taxableGain()).isEqualTo(-10.0);       // loss stands
    }

    @Test
    void traderMarkToMarketTaxesUnrealizedGainsAsOrdinary() {
        // §475(f): the open position is marked to market at period end, all ordinary.
        List<TaxTrade> trades = List.of(trade("2026-01-01T00:00:00Z", "BUY", 1, 100));

        TaxReport r = engine.compute(new TaxRequest("CRYPTO", "FIFO", "TRADER_MTM", 0.37, 0.20, 120.0, trades));

        assertThat(r.unrealizedMtm()).isEqualTo(20.0);
        assertThat(r.taxableGain()).isEqualTo(20.0);
        assertThat(r.longTermGain()).isEqualTo(0.0);           // no long-term under MTM
        assertThat(r.taxOwed()).isCloseTo(7.4, within(1e-6));  // 20 * ordinary 37%
    }

    // --- Regression tests for bugs the earlier suite missed ---

    @Test
    void plainLossRoundTripIsNotAWashSale() {
        // Buy, then sell at a loss within 30 days, with NO replacement purchase. The sold
        // lot's own originating buy must NOT count as its replacement. (Regression: the old
        // code disallowed the loss on every closed losing trade.)
        List<TaxTrade> trades = List.of(
                trade("2026-01-01T00:00:00Z", "BUY", 100, 10),
                trade("2026-01-10T00:00:00Z", "SELL", 100, 8)); // -200 loss, nothing rebought

        TaxReport r = engine.compute(new TaxRequest("EQUITY", "FIFO", "RETAIL", null, null, null, trades));

        assertThat(r.washSaleDisallowed()).isEqualTo(0.0);
        assertThat(r.taxableGain()).isEqualTo(-200.0); // the loss stands
    }

    @Test
    void oneReplacementCannotWashTwoSeparateLosses() {
        // Two losing sales but only one 100-share replacement → at most $500 disallowed, not
        // $1000 (replacement capacity is consumed). Buys are spaced >30 days from the sales so
        // only the rebuy is a candidate.
        List<TaxTrade> trades = List.of(
                trade("2026-01-01T00:00:00Z", "BUY", 100, 10),
                trade("2026-01-02T00:00:00Z", "BUY", 100, 10),
                trade("2026-03-01T00:00:00Z", "SELL", 100, 5),   // -500 (lot 1)
                trade("2026-03-02T00:00:00Z", "SELL", 100, 5),   // -500 (lot 2)
                trade("2026-03-10T00:00:00Z", "BUY", 100, 5));    // one 100-share replacement

        TaxReport r = engine.compute(new TaxRequest("EQUITY", "FIFO", "RETAIL", null, null, null, trades));

        assertThat(r.washSaleDisallowed()).isEqualTo(500.0);
    }

    @Test
    void exactlyOneYearHoldSpanningALeapDayIsShortTerm() {
        // 2020 is a leap year → 366 days, but one calendar year is NOT "more than one year".
        List<TaxTrade> trades = List.of(
                trade("2020-01-01T00:00:00Z", "BUY", 1, 100),
                trade("2021-01-01T00:00:00Z", "SELL", 1, 120));

        TaxReport r = engine.compute(new TaxRequest("CRYPTO", "FIFO", "RETAIL", 0.37, 0.20, null, trades));

        assertThat(r.shortTermGain()).isEqualTo(20.0);
        assertThat(r.longTermGain()).isEqualTo(0.0);
    }

    @Test
    void biasCallout_shortAndLongTermAreNotNetted() {
        // KNOWN SIMPLIFICATION (documented): a short-term loss and an equal long-term gain net
        // to zero economically, but taxing them at their own rates (37% vs 20%) yields an
        // artificial benefit. Real IRS netting rules would cancel them. This test PINS the
        // direction of the bias so it can't drift silently.
        List<TaxTrade> trades = List.of(
                trade("2020-01-01T00:00:00Z", "BUY", 1, 100),   // long-term lot
                trade("2026-01-01T00:00:00Z", "BUY", 1, 100),   // short-term lot
                trade("2026-01-05T00:00:00Z", "SELL", 1, 80),   // LIFO sells the ST lot: -20 ST loss
                trade("2026-02-01T00:00:00Z", "SELL", 1, 120)); // then the LT lot: +20 LT gain

        TaxReport r = engine.compute(new TaxRequest("CRYPTO", "LIFO", "RETAIL", 0.37, 0.20, null, trades));

        assertThat(r.preTaxPnl()).isEqualTo(0.0);        // economically break-even
        assertThat(r.taxOwed()).isLessThan(0.0);         // yet a net tax "benefit" — the bias
        assertThat(r.afterTaxPnl()).isGreaterThan(0.0);
    }
}
