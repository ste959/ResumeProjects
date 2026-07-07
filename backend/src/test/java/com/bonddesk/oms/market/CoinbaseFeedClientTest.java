package com.bonddesk.oms.market;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit tests for the Coinbase Advanced Trade feed parsing — driven by captured JSON frames
 * through the package-private {@link CoinbaseFeedClient#handle} seam, with no live socket.
 */
class CoinbaseFeedClientTest {

    private final ObjectMapper json = new ObjectMapper();
    private final MarketDataService marketData = new MarketDataService(new CoinbaseProperties());
    private final CoinbaseFeedClient client =
            new CoinbaseFeedClient(new CoinbaseProperties(), marketData, json, Optional.empty());

    private void feed(String frame) throws Exception {
        client.handle(json.readTree(frame));
    }

    private static final String SNAPSHOT = """
            {"channel":"l2_data","sequence_num":0,"events":[
              {"type":"snapshot","product_id":"BTC-USD","updates":[
                {"side":"bid","price_level":"100.00","new_quantity":"2"},
                {"side":"bid","price_level":"99.50","new_quantity":"5"},
                {"side":"offer","price_level":"100.50","new_quantity":"3"},
                {"side":"offer","price_level":"101.00","new_quantity":"1"}
              ]}
            ]}""";

    @Test
    void level2SnapshotPopulatesBook() throws Exception {
        feed(SNAPSHOT);

        LiveOrderBook book = marketData.book("BTC-USD");
        assertThat(book.bestBid()).isEqualByComparingTo("100.00");
        assertThat(book.bestAsk()).isEqualByComparingTo("100.50");
        assertThat(book.bestBidSize()).isEqualByComparingTo("2");
        assertThat(book.bestAskSize()).isEqualByComparingTo("3");
    }

    @Test
    void level2UpdateAddsBetterLevelAndRemovesOnZeroQuantity() throws Exception {
        feed(SNAPSHOT);
        // A new best bid at 100.25, and the 100.50 ask cleared (new_quantity 0 removes it).
        feed("""
                {"channel":"l2_data","sequence_num":1,"events":[
                  {"type":"update","product_id":"BTC-USD","updates":[
                    {"side":"bid","price_level":"100.25","new_quantity":"4"},
                    {"side":"offer","price_level":"100.50","new_quantity":"0"}
                  ]}
                ]}""");

        LiveOrderBook book = marketData.book("BTC-USD");
        assertThat(book.bestBid()).isEqualByComparingTo("100.25");
        assertThat(book.bestBidSize()).isEqualByComparingTo("4");
        assertThat(book.bestAsk()).isEqualByComparingTo("101.00"); // 100.50 removed
    }

    @Test
    void marketTradeUpdatesTapeAndLastPrice() throws Exception {
        feed("""
                {"channel":"market_trades","events":[
                  {"type":"update","trades":[
                    {"trade_id":"42","product_id":"BTC-USD","price":"100.25","size":"0.5",
                     "side":"BUY","time":"2026-01-02T03:04:05Z"}
                  ]}
                ]}""");

        assertThat(marketData.lastPrice("BTC-USD")).isEqualByComparingTo("100.25");
        List<TradePrint> tape = marketData.recentTrades("BTC-USD");
        assertThat(tape).hasSize(1);
        assertThat(tape.get(0).price()).isEqualByComparingTo("100.25");
        assertThat(tape.get(0).size()).isEqualByComparingTo("0.5");
        assertThat(tape.get(0).side()).isEqualTo("BUY");
    }

    @Test
    void unknownChannelIsIgnored() throws Exception {
        feed("""
                {"channel":"heartbeats","events":[{"current_time":"2026-01-02T03:04:05Z"}]}""");
        assertThat(marketData.book("BTC-USD").isReady()).isFalse();
    }
}
