package com.bonddesk.oms.market.stream;

import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.MarketDataService;
import com.bonddesk.oms.market.stream.MarketSocketHandler.Subscription;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** The subscribe/registry/send contract of the live market-data WebSocket handler. */
class MarketSocketHandlerTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private MarketSocketHandler newHandler() {
        MarketDataService marketData = mock(MarketDataService.class);
        when(marketData.currentTradeSeq()).thenReturn(7L);
        when(marketData.book("BTC-USD")).thenReturn(new LiveOrderBook("BTC-USD"));
        return new MarketSocketHandler(mapper, marketData);
    }

    private WebSocketSession session(String id) {
        WebSocketSession s = mock(WebSocketSession.class);
        when(s.getId()).thenReturn(id);
        when(s.isOpen()).thenReturn(true);
        return s;
    }

    @Test
    void subscribeRegistersProductAndInitializesCursor() {
        MarketSocketHandler handler = newHandler();
        WebSocketSession session = session("s1");

        handler.afterConnectionEstablished(session);
        handler.handleTextMessage(session, new TextMessage("{\"subscribe\":\"BTC-USD\"}"));

        assertThat(handler.subscriptions()).hasSize(1);
        Subscription sub = handler.subscriptions().iterator().next();
        assertThat(sub.product()).isEqualTo("BTC-USD");
        assertThat(sub.lastTradeSeq).isEqualTo(7L); // cursor seeded so the first tick doesn't replay the tape
    }

    @Test
    void sendSerializesFrameToOpenSession() throws Exception {
        MarketSocketHandler handler = newHandler();
        WebSocketSession session = session("s1");
        handler.afterConnectionEstablished(session);
        handler.handleTextMessage(session, new TextMessage("{\"subscribe\":\"BTC-USD\"}"));
        Subscription sub = handler.subscriptions().iterator().next();

        handler.send(sub, Map.of("type", "book", "product", "BTC-USD"));

        verify(session, times(1)).sendMessage(any(TextMessage.class));
    }

    @Test
    void closeRemovesSubscription() {
        MarketSocketHandler handler = newHandler();
        WebSocketSession session = session("s1");
        handler.afterConnectionEstablished(session);
        assertThat(handler.subscriptions()).hasSize(1);

        handler.afterConnectionClosed(session, CloseStatus.NORMAL);
        assertThat(handler.subscriptions()).isEmpty();
    }

    @Test
    void malformedControlMessageIsIgnored() {
        MarketSocketHandler handler = newHandler();
        WebSocketSession session = session("s1");
        handler.afterConnectionEstablished(session);

        handler.handleTextMessage(session, new TextMessage("not json"));

        // Still registered, just no product set — the stream simply won't start for this client.
        assertThat(handler.subscriptions()).hasSize(1);
        assertThat(handler.subscriptions().iterator().next().product()).isNull();
    }
}
