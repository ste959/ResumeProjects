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
}
