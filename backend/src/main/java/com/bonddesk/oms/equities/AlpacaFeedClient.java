package com.bonddesk.oms.equities;

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
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

/**
 * Streams live equity quotes and trades from Alpaca's market-data websocket (free IEX
 * feed) into {@link EquityMarketDataService}. Unlike the public Coinbase feed, Alpaca
 * requires authentication, so the handshake is: connect → {@code auth} → {@code subscribe}.
 *
 * <p>Uses the JDK's built-in {@link WebSocket} client — no third-party dependency. If no
 * API credentials are configured the client stays idle so the app still boots cleanly.
 */
@Component
@ConditionalOnProperty(prefix = "oms.equities", name = "enabled", havingValue = "true", matchIfMissing = true)
public class AlpacaFeedClient {

    private static final Logger log = LoggerFactory.getLogger(AlpacaFeedClient.class);

    private final AlpacaProperties props;
    private final EquityMarketDataService marketData;
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newHttpClient();
    private final ScheduledExecutorService reconnect = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "alpaca-feed");
        t.setDaemon(true);
        return t;
    });

    private volatile boolean running = true;
    private volatile WebSocket webSocket;

    public AlpacaFeedClient(AlpacaProperties props, EquityMarketDataService marketData, ObjectMapper json) {
        this.props = props;
        this.marketData = marketData;
        this.json = json;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        if (!props.hasCredentials()) {
            log.info("Alpaca credentials not set — equities feed idle. Add keys to alpaca-local.yml "
                    + "(or ALPACA_KEY_ID / ALPACA_SECRET_KEY) to enable the live equity market.");
            return;
        }
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
        log.info("Connecting to Alpaca feed {} for {}", props.getDataWsUrl(), props.getSymbols());
        http.newWebSocketBuilder()
                .buildAsync(URI.create(props.getDataWsUrl()), new FeedListener())
                .whenComplete((ws, err) -> {
                    if (err != null) {
                        log.warn("Alpaca connect failed ({}); retrying in 5s", err.getMessage());
                        scheduleReconnect();
                    }
                });
    }

    private void scheduleReconnect() {
        if (running) {
            reconnect.schedule(this::connect, 5, TimeUnit.SECONDS);
        }
    }

    private void sendAuth(WebSocket ws) {
        ws.sendText("{\"action\":\"auth\",\"key\":\"" + props.getKeyId()
                + "\",\"secret\":\"" + props.getSecretKey() + "\"}", true);
    }

    private void sendSubscribe(WebSocket ws) {
        String syms = props.getSymbols().stream()
                .map(s -> "\"" + s + "\"")
                .collect(Collectors.joining(","));
        ws.sendText("{\"action\":\"subscribe\",\"quotes\":[" + syms + "],\"trades\":[" + syms + "]}", true);
    }

    /** Handles the WebSocket lifecycle and message parsing. */
    private final class FeedListener implements WebSocket.Listener {
        private final StringBuilder buffer = new StringBuilder();

        @Override
        public void onOpen(WebSocket ws) {
            webSocket = ws;
            log.info("Alpaca feed connected; authenticating");
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
            buffer.append(data);
            if (last) {
                String message = buffer.toString();
                buffer.setLength(0);
                try {
                    // Alpaca batches messages as a JSON array.
                    for (JsonNode node : json.readTree(message)) {
                        handle(ws, node);
                    }
                } catch (Exception e) {
                    log.debug("Failed to handle Alpaca message: {}", e.getMessage());
                }
            }
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
            log.warn("Alpaca feed closed ({} {}); reconnecting", statusCode, reason);
            scheduleReconnect();
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            log.warn("Alpaca feed error ({}); reconnecting", error.getMessage());
            scheduleReconnect();
        }
    }

    /** Parse and apply one decoded feed message (or drive the auth handshake). Package-private
     * so it can be unit-tested with captured JSON frames and a stub socket. */
    void handle(WebSocket ws, JsonNode node) {
        switch (node.path("T").asText()) {
            case "success" -> {
                String msg = node.path("msg").asText();
                if ("connected".equals(msg)) {
                    sendAuth(ws);
                } else if ("authenticated".equals(msg)) {
                    log.info("Alpaca authenticated; subscribing to {}", props.getSymbols());
                    sendSubscribe(ws);
                }
            }
            case "error" -> log.warn("Alpaca feed error {}: {}",
                    node.path("code").asInt(), node.path("msg").asText());
            case "subscription" -> log.info("Alpaca subscription active");
            case "q" -> applyQuote(node);
            case "t" -> applyTrade(node);
            default -> { /* bars and other message types ignored */ }
        }
    }

    private void applyQuote(JsonNode q) {
        marketData.updateQuote(
                q.path("S").asText(),
                new BigDecimal(q.path("bp").asText("0")),
                new BigDecimal(q.path("ap").asText("0")),
                new BigDecimal(q.path("bs").asText("0")),
                new BigDecimal(q.path("as").asText("0")),
                parseTime(q.path("t").asText()));
    }

    private void applyTrade(JsonNode t) {
        marketData.recordTrade(
                t.path("S").asText(),
                new BigDecimal(t.path("p").asText("0")),
                new BigDecimal(t.path("s").asText("0")),
                parseTime(t.path("t").asText()));
    }

    private static Instant parseTime(String iso) {
        try {
            return Instant.parse(iso);
        } catch (Exception e) {
            return Instant.now();
        }
    }
}
