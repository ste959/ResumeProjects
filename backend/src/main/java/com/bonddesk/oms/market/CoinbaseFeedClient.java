package com.bonddesk.oms.market;

import com.bonddesk.oms.market.LiveOrderBook.Level;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import jakarta.annotation.PreDestroy;
import java.math.BigDecimal;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Streams the live Coinbase order book (Advanced Trade {@code level2}) and trade tape
 * ({@code market_trades}) over a WebSocket and feeds {@link MarketDataService}. Market
 * data on these channels is public, so no API key is needed. Reconnects with backoff.
 *
 * <p>Uses the JDK's built-in {@link WebSocket} client — no third-party dependency.
 */
@Component
@ConditionalOnProperty(prefix = "oms.crypto", name = "enabled", havingValue = "true", matchIfMissing = true)
public class CoinbaseFeedClient {

    private static final Logger log = LoggerFactory.getLogger(CoinbaseFeedClient.class);

    private final CoinbaseProperties props;
    private final MarketDataService marketData;
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newHttpClient();
    private final ScheduledExecutorService reconnect = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "coinbase-feed");
        t.setDaemon(true);
        return t;
    });

    private volatile boolean running = true;
    private volatile WebSocket webSocket;

    public CoinbaseFeedClient(CoinbaseProperties props, MarketDataService marketData, ObjectMapper json) {
        this.props = props;
        this.marketData = marketData;
        this.json = json;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        connect();
    }

    @PreDestroy
    public void stop() {
        running = false;
        reconnect.shutdownNow();
        WebSocket ws = webSocket;
        if (ws != null) {
            ws.sendClose(WebSocket.NORMAL_CLOSURE, "shutdown");
        }
    }

    private void connect() {
        if (!running) {
            return;
        }
        log.info("Connecting to Coinbase feed {} for {}", props.getWsUrl(), props.getProducts());
        http.newWebSocketBuilder()
                .buildAsync(URI.create(props.getWsUrl()), new FeedListener())
                .whenComplete((ws, err) -> {
                    if (err != null) {
                        log.warn("Coinbase connect failed ({}); retrying in 5s", err.getMessage());
                        scheduleReconnect();
                    }
                });
    }

    private void scheduleReconnect() {
        if (running) {
            reconnect.schedule(this::connect, 5, TimeUnit.SECONDS);
        }
    }

    private String subscribe(String channel) {
        String ids = props.getProducts().stream()
                .map(p -> "\"" + p + "\"")
                .reduce((a, b) -> a + "," + b).orElse("");
        return "{\"type\":\"subscribe\",\"product_ids\":[" + ids + "],\"channel\":\"" + channel + "\"}";
    }

    /** Handles the WebSocket lifecycle and message parsing. */
    private final class FeedListener implements WebSocket.Listener {
        private final StringBuilder buffer = new StringBuilder();

        @Override
        public void onOpen(WebSocket ws) {
            webSocket = ws;
            log.info("Coinbase feed connected");
            ws.sendText(subscribe("level2"), true);
            ws.sendText(subscribe("market_trades"), true);
            ws.sendText(subscribe("heartbeats"), true);
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
            buffer.append(data);
            if (last) {
                String message = buffer.toString();
                buffer.setLength(0);
                try {
                    handle(json.readTree(message));
                } catch (Exception e) {
                    log.debug("Failed to handle feed message: {}", e.getMessage());
                }
            }
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
            log.warn("Coinbase feed closed ({} {}); reconnecting", statusCode, reason);
            scheduleReconnect();
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            log.warn("Coinbase feed error ({}); reconnecting", error.getMessage());
            scheduleReconnect();
        }
    }

    private void handle(JsonNode root) {
        String channel = root.path("channel").asText();
        switch (channel) {
            case "l2_data" -> root.path("events").forEach(this::applyBookEvent);
            case "market_trades" -> root.path("events").forEach(this::applyTradeEvent);
            default -> { /* subscriptions, heartbeats, etc. */ }
        }
    }

    private void applyBookEvent(JsonNode event) {
        String product = event.path("product_id").asText();
        LiveOrderBook book = marketData.book(product);
        boolean snapshot = "snapshot".equals(event.path("type").asText());
        if (snapshot) {
            List<Level> bids = new ArrayList<>();
            List<Level> asks = new ArrayList<>();
            for (JsonNode u : event.path("updates")) {
                Level level = new Level(new BigDecimal(u.path("price_level").asText()),
                        new BigDecimal(u.path("new_quantity").asText()));
                if ("bid".equals(u.path("side").asText())) {
                    bids.add(level);
                } else {
                    asks.add(level);
                }
            }
            book.resetTo(bids, asks);
        } else {
            for (JsonNode u : event.path("updates")) {
                book.apply("bid".equals(u.path("side").asText()),
                        new BigDecimal(u.path("price_level").asText()),
                        new BigDecimal(u.path("new_quantity").asText()));
            }
        }
    }

    private void applyTradeEvent(JsonNode event) {
        for (JsonNode t : event.path("trades")) {
            marketData.recordTrade(new TradePrint(
                    t.path("product_id").asText(),
                    new BigDecimal(t.path("price").asText()),
                    new BigDecimal(t.path("size").asText()),
                    t.path("side").asText(),
                    parseTime(t.path("time").asText())));
        }
    }

    private static Instant parseTime(String iso) {
        try {
            return Instant.parse(iso);
        } catch (Exception e) {
            return Instant.now();
        }
    }
}
