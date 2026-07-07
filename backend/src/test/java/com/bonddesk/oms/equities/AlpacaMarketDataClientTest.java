package com.bonddesk.oms.equities;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit tests for the Alpaca snapshot JSON parsing via the package-private {@code parseSnapshots}
 * seam — no live feed. Verifies latest-trade extraction, quote-midpoint fallback, non-positive
 * skipping, and the {@code snapshots}-wrapper variant.
 */
class AlpacaMarketDataClientTest {

    private final ObjectMapper json = new ObjectMapper();
    private final AlpacaMarketDataClient client = new AlpacaMarketDataClient(new AlpacaProperties(), json);

    private Map<String, BigDecimal> parse(String body) {
        Map<String, BigDecimal> out = new HashMap<>();
        client.parseSnapshots(body, out);
        return out;
    }

    @Test
    void usesLatestTradePriceWhenPresent() {
        Map<String, BigDecimal> prices = parse("""
                {"AAPL":{"latestTrade":{"p":190.12},"latestQuote":{"ap":190.20,"bp":190.10}}}""");

        assertThat(prices.get("AAPL")).isEqualByComparingTo("190.12");
    }

    @Test
    void fallsBackToQuoteMidpointWhenTradeMissing() {
        Map<String, BigDecimal> prices = parse("""
                {"MSFT":{"latestQuote":{"ap":300.00,"bp":299.00}}}""");

        assertThat(prices.get("MSFT")).isEqualByComparingTo("299.50");
    }

    @Test
    void fallsBackToMidpointWhenTradePriceIsZero() {
        Map<String, BigDecimal> prices = parse("""
                {"NVDA":{"latestTrade":{"p":0},"latestQuote":{"ap":120.00,"bp":118.00}}}""");

        assertThat(prices.get("NVDA")).isEqualByComparingTo("119.00");
    }

    @Test
    void skipsSymbolWithNoUsablePrice() {
        Map<String, BigDecimal> prices = parse("""
                {"AMZN":{"latestTrade":{"p":0},"latestQuote":{"ap":0,"bp":0}}}""");

        assertThat(prices).doesNotContainKey("AMZN");
    }

    @Test
    void parsesMultipleSymbolsAndSnapshotsWrapper() {
        Map<String, BigDecimal> prices = parse("""
                {"snapshots":{"AAPL":{"latestTrade":{"p":190.00}},
                              "JPM":{"latestTrade":{"p":210.50}}}}""");

        assertThat(prices).hasSize(2);
        assertThat(prices.get("AAPL")).isEqualByComparingTo("190.00");
        assertThat(prices.get("JPM")).isEqualByComparingTo("210.50");
    }

    @Test
    void returnsEmptyWithoutCredentials() {
        // Default AlpacaProperties has blank keys → no credentials → no network call, empty map.
        assertThat(client.latestPrices(java.util.List.of("AAPL"))).isEmpty();
    }

    @Test
    void unparseableBodyYieldsEmptyRatherThanThrowing() {
        assertThat(parse("not json at all")).isEmpty();
    }
}
