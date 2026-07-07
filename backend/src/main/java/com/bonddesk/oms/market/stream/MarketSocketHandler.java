package com.bonddesk.oms.market.stream;

import com.bonddesk.oms.market.MarketDataService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.util.Collection;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * The server side of the live market-data WebSocket. Browsers connect to {@code /ws/market} and send
 * a single subscribe message — {@code {"subscribe":"BTC-USD"}} — to choose a product; the
 * {@link MarketStreamBroadcaster} then pushes book / trade / metrics frames to them on a timer.
 *
 * <p>This handler owns only session bookkeeping and sending; it never touches the book on the feed
 * thread. Sends are synchronized per session because both this thread (the immediate snapshot on
 * subscribe) and the broadcaster thread can write to the same session.
 */
@Component
@ConditionalOnProperty(name = "oms.crypto.enabled", matchIfMissing = true)
public class MarketSocketHandler extends TextWebSocketHandler {

    /** One connected client: its session, the product it watches, and its stream cursors. */
    public static final class Subscription {
        final WebSocketSession session;
        volatile String product;            // null until the client subscribes
        long lastTradeSeq;                  // cursor into the trade tape (broadcaster thread only)
        long lastUpdateCount;               // book-update counter at the last tick
        long lastTickMillis;                // wall clock of the last tick (0 = first)

        Subscription(WebSocketSession session) {
            this.session = session;
        }

        public String product() {
            return product;
        }
    }

    private final Map<String, Subscription> subscriptions = new ConcurrentHashMap<>();
    private final ObjectMapper mapper;
    private final MarketDataService marketData;

    public MarketSocketHandler(ObjectMapper mapper, MarketDataService marketData) {
        this.mapper = mapper;
        this.marketData = marketData;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        subscriptions.put(session.getId(), new Subscription(session));
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        try {
            JsonNode node = mapper.readTree(message.getPayload());
            JsonNode sub = node.get("subscribe");
            if (sub == null || sub.asText().isBlank()) {
                return;
            }
            String product = sub.asText();
            Subscription s = subscriptions.get(session.getId());
            if (s != null) {
                // Initialize cursors BEFORE exposing the product so the first tick doesn't replay the
                // whole existing tape or report a bogus first-interval update rate.
                s.lastTradeSeq = marketData.currentTradeSeq();
                s.lastUpdateCount = marketData.book(product).updateCount();
                s.lastTickMillis = 0;
                s.product = product;
            }
        } catch (Exception ignored) {
            // Malformed control message — ignore; the stream just won't start for this client.
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        subscriptions.remove(session.getId());
    }

    /** Live subscriptions, for the broadcaster to iterate. */
    public Collection<Subscription> subscriptions() {
        return subscriptions.values();
    }

    /** Serialize and send a frame to one subscriber. Silently drops on a closed/broken session. */
    public void send(Subscription sub, Object frame) {
        WebSocketSession session = sub.session;
        try {
            String json = mapper.writeValueAsString(frame);
            synchronized (session) {
                if (session.isOpen()) {
                    session.sendMessage(new TextMessage(json));
                }
            }
        } catch (Exception ignored) {
            // Client went away mid-send; afterConnectionClosed will clean up the registry.
        }
    }
}
