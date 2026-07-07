package com.bonddesk.oms.equities;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

/**
 * Reads live equity marks from Alpaca's REST snapshot endpoint so the rebalance path can size
 * against current prices rather than the (possibly stale) target-book reference prices. Uses the
 * IEX feed (free tier) and the same {@code APCA-API-*} auth headers as the broker client.
 *
 * <p>Every parse is guarded and every failure degrades to "return what we have": a missing or
 * unreachable feed yields an empty map, which the rebalance treats as "no override" and falls
 * back to the target-book price — so live pricing can never break the paper trading loop.
 */
@Component
public class AlpacaMarketDataClient {

    private static final Logger log = LoggerFactory.getLogger(AlpacaMarketDataClient.class);

    /** Alpaca caps a snapshot request at 100 symbols; chunk larger requests. */
    private static final int MAX_SYMBOLS_PER_CALL = 100;

    private final AlpacaProperties props;
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    public AlpacaMarketDataClient(AlpacaProperties props, ObjectMapper json) {
        this.props = props;
        this.json = json;
    }

    /**
     * Latest trade price per symbol (falling back to the quote midpoint when no trade is present).
     * Non-positive or unparseable marks are skipped. Returns an empty map when credentials are
     * absent; on a partial failure returns whatever chunks succeeded.
     */
    public Map<String, BigDecimal> latestPrices(Collection<String> symbols) {
        Map<String, BigDecimal> out = new HashMap<>();
        if (!props.hasCredentials() || symbols == null || symbols.isEmpty()) {
            return out;
        }
        // De-dupe and drop blanks while preserving order.
        LinkedHashSet<String> unique = new LinkedHashSet<>();
        for (String s : symbols) {
            if (s != null && !s.isBlank()) {
                unique.add(s.trim());
            }
        }
        List<String> list = new ArrayList<>(unique);
        for (int i = 0; i < list.size(); i += MAX_SYMBOLS_PER_CALL) {
            List<String> chunk = list.subList(i, Math.min(i + MAX_SYMBOLS_PER_CALL, list.size()));
            try {
                fetchChunk(chunk, out);
            } catch (RuntimeException e) {
                log.debug("Snapshot fetch for {} symbols failed: {}", chunk.size(), e.getMessage());
                // Keep whatever earlier chunks produced.
            }
        }
        return out;
    }

    private void fetchChunk(List<String> chunk, Map<String, BigDecimal> out) {
        String csv = String.join(",", chunk);
        String encoded = URLEncoder.encode(csv, StandardCharsets.UTF_8);
        HttpResponse<String> res = send(HttpRequest.newBuilder()
                .uri(URI.create(props.getDataBaseUrl() + "/v2/stocks/snapshots?symbols=" + encoded + "&feed=iex"))
                .GET());
        if (res.statusCode() / 100 != 2) {
            log.debug("Alpaca snapshot returned {}", res.statusCode());
            return;
        }
        parseSnapshots(res.body(), out);
    }

    /**
     * Parse a snapshots response body into {@code out}. The endpoint returns a top-level object
     * mapping symbol -> snapshot (some responses nest it under {@code "snapshots"}); handle both.
     * Package-private so the parse can be unit-tested against captured JSON.
     */
    void parseSnapshots(String body, Map<String, BigDecimal> out) {
        JsonNode root;
        try {
            root = json.readTree(body);
        } catch (Exception e) {
            log.debug("Unparseable snapshot response: {}", e.getMessage());
            return;
        }
        JsonNode map = root.has("snapshots") ? root.path("snapshots") : root;
        Iterator<Map.Entry<String, JsonNode>> fields = map.fields();
        while (fields.hasNext()) {
            Map.Entry<String, JsonNode> e = fields.next();
            BigDecimal price = markOf(e.getValue());
            if (price != null && price.signum() > 0) {
                out.put(e.getKey(), price);
            }
        }
    }

    /** The mark for one snapshot node: latest trade price, else the quote midpoint; null if neither. */
    private BigDecimal markOf(JsonNode snapshot) {
        if (snapshot == null || !snapshot.isObject()) {
            return null;
        }
        BigDecimal trade = positive(snapshot.path("latestTrade").path("p"));
        if (trade != null) {
            return trade;
        }
        BigDecimal ask = positive(snapshot.path("latestQuote").path("ap"));
        BigDecimal bid = positive(snapshot.path("latestQuote").path("bp"));
        if (ask != null && bid != null) {
            return ask.add(bid).divide(BigDecimal.valueOf(2));
        }
        return null;
    }

    /** A strictly-positive BigDecimal from a numeric/text node, or null (never throws). */
    private static BigDecimal positive(JsonNode node) {
        if (node == null || node.isMissingNode() || node.isNull()) {
            return null;
        }
        try {
            String text = node.asText();
            if (text == null || text.isBlank()) {
                return null;
            }
            BigDecimal v = new BigDecimal(text);
            return v.signum() > 0 ? v : null;
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private HttpResponse<String> send(HttpRequest.Builder builder) {
        try {
            HttpRequest req = builder
                    .header("APCA-API-KEY-ID", props.getKeyId())
                    .header("APCA-API-SECRET-KEY", props.getSecretKey())
                    .timeout(Duration.ofSeconds(15))
                    .build();
            return http.send(req, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new IllegalStateException("Alpaca market-data request failed: " + e.getMessage(), e);
        }
    }
}
