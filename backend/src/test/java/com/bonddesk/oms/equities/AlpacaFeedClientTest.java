package com.bonddesk.oms.equities;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.http.WebSocket;
import java.util.concurrent.CompletableFuture;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for the Alpaca feed parsing/handshake — driven by captured JSON frames through
 * the package-private {@link AlpacaFeedClient#handle} seam with a stub socket, no live stream.
 */
class AlpacaFeedClientTest {

    private final ObjectMapper json = new ObjectMapper();
    private final EquityMarketDataService marketData = new EquityMarketDataService(new AlpacaProperties());
    private final AlpacaFeedClient client = new AlpacaFeedClient(new AlpacaProperties(), marketData, json);

    private void handle(WebSocket ws, String frame) throws Exception {
        client.handle(ws, json.readTree(frame));
    }

    @Test
    void quoteMessageUpdatesNbbo() throws Exception {
        handle(mock(WebSocket.class), """
                {"T":"q","S":"AAPL","bp":"190.10","ap":"190.15","bs":"3","as":"4","t":"2026-01-02T03:04:05Z"}""");

        EquityQuote q = marketData.quote("AAPL");
        assertThat(q).isNotNull();
        assertThat(q.bid()).isEqualByComparingTo("190.10");
        assertThat(q.ask()).isEqualByComparingTo("190.15");
        assertThat(q.bidSize()).isEqualByComparingTo("3");
        assertThat(q.askSize()).isEqualByComparingTo("4");
    }

    @Test
    void tradeMessageRecordsPrintAndLastPrice() throws Exception {
        handle(mock(WebSocket.class), """
                {"T":"t","S":"AAPL","p":"190.12","s":"100","t":"2026-01-02T03:04:05Z"}""");

        assertThat(marketData.lastPrice("AAPL")).isEqualByComparingTo("190.12");
        assertThat(marketData.recentTrades("AAPL")).hasSize(1);
        assertThat(marketData.recentTrades("AAPL").get(0).price()).isEqualByComparingTo("190.12");
    }

    @Test
    void connectedMessageDrivesAuthHandshake() throws Exception {
        WebSocket ws = mock(WebSocket.class);
        when(ws.sendText(any(CharSequence.class), anyBoolean()))
                .thenReturn(CompletableFuture.completedFuture(ws));

        handle(ws, """
                {"T":"success","msg":"connected"}""");

        verify(ws).sendText(contains("\"action\":\"auth\""), eq(true));
    }
}
