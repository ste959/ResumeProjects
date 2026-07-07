package com.bonddesk.oms.equities;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderType;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
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

/**
 * Thin REST client for the Alpaca (paper) trading API. Submits equity orders to the
 * broker, looks them up by our order reference, and cancels them. This is the venue side
 * of the OMS: our order lifecycle drives, Alpaca executes against the real market.
 *
 * <p>Uses the JDK {@link HttpClient} with the standard {@code APCA-API-*} auth headers.
 */
@Component
public class AlpacaBrokerClient {

    private static final Logger log = LoggerFactory.getLogger(AlpacaBrokerClient.class);

    private final AlpacaProperties props;
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    public AlpacaBrokerClient(AlpacaProperties props, ObjectMapper json) {
        this.props = props;
        this.json = json;
    }

    /** Broker's view of an order after submission or reconciliation. */
    public record AlpacaOrder(String id, String clientOrderId, String symbol, String status,
                              BigDecimal filledQty, BigDecimal filledAvgPrice) {
    }

    /** Paper account summary, for display. */
    public record AccountInfo(String status, BigDecimal cash, BigDecimal buyingPower,
                              BigDecimal equity, String currency) {
    }

    /** Broker's tradability metadata for a symbol. */
    public record AlpacaAsset(String symbol, boolean tradable, boolean shortable) {
    }

    /** True when broker credentials are present, so the venue can be called. */
    public boolean brokerReachable() {
        return props.hasCredentials();
    }

    /**
     * Whether the venue will accept a short sale of {@code symbol}: the asset must be both
     * tradable and shortable. Returns false (never throws) on any error or when credentials
     * are absent, so the rebalance path can safely skip a name it cannot short.
     */
    public boolean isShortable(String symbol) {
        if (!props.hasCredentials()) {
            log.debug("Shortability check for {} skipped — no Alpaca credentials", symbol);
            return false;
        }
        try {
            String encoded = URLEncoder.encode(symbol, StandardCharsets.UTF_8);
            HttpResponse<String> res = send(HttpRequest.newBuilder()
                    .uri(URI.create(props.getTradingBaseUrl() + "/v2/assets/" + encoded))
                    .GET());
            if (res.statusCode() / 100 != 2) {
                log.debug("Alpaca asset lookup for {} returned {}", symbol, res.statusCode());
                return false;
            }
            JsonNode n = readTree(res.body());
            AlpacaAsset asset = new AlpacaAsset(
                    n.path("symbol").asText(symbol),
                    n.path("tradable").asBoolean(false),
                    n.path("shortable").asBoolean(false));
            return asset.shortable() && asset.tradable();
        } catch (RuntimeException e) {
            log.debug("Shortability check for {} failed: {}", symbol, e.getMessage());
            return false;
        }
    }

    /** Submit a new order to Alpaca, tagging it with our order reference as client_order_id. */
    public AlpacaOrder submit(Order order) {
        ObjectNode body = json.createObjectNode();
        body.put("symbol", order.getSecurity().getTicker());
        body.put("qty", order.getQuantity().stripTrailingZeros().toPlainString());
        body.put("side", order.getSide().name().toLowerCase());
        body.put("type", order.getOrderType() == OrderType.LIMIT ? "limit" : "market");
        body.put("time_in_force", order.getTimeInForce().name().toLowerCase());
        body.put("client_order_id", order.getOrderRef());
        if (order.getOrderType() == OrderType.LIMIT && order.getLimitPrice() != null) {
            body.put("limit_price", order.getLimitPrice().toPlainString());
        }
        HttpResponse<String> res = send(HttpRequest.newBuilder()
                .uri(URI.create(props.getTradingBaseUrl() + "/v2/orders"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body.toString())));
        if (res.statusCode() / 100 != 2) {
            throw new IllegalStateException("Alpaca order rejected (" + res.statusCode() + "): " + res.body());
        }
        return parseOrder(readTree(res.body()));
    }

    /** Fetch an order by our reference (client_order_id); null if the broker has none. */
    public AlpacaOrder getByClientOrderId(String orderRef) {
        String encoded = URLEncoder.encode(orderRef, StandardCharsets.UTF_8);
        HttpResponse<String> res = send(HttpRequest.newBuilder()
                .uri(URI.create(props.getTradingBaseUrl() + "/v2/orders:by_client_order_id?client_order_id=" + encoded))
                .GET());
        if (res.statusCode() == 404) {
            return null;
        }
        if (res.statusCode() / 100 != 2) {
            throw new IllegalStateException("Alpaca lookup failed (" + res.statusCode() + "): " + res.body());
        }
        return parseOrder(readTree(res.body()));
    }

    /** Cancel a working order at the broker. Best-effort. */
    public void cancel(String alpacaOrderId) {
        HttpResponse<String> res = send(HttpRequest.newBuilder()
                .uri(URI.create(props.getTradingBaseUrl() + "/v2/orders/" + alpacaOrderId))
                .DELETE());
        if (res.statusCode() / 100 != 2 && res.statusCode() != 404) {
            log.debug("Alpaca cancel of {} returned {}", alpacaOrderId, res.statusCode());
        }
    }

    /** Paper account summary; null if unavailable. */
    public AccountInfo account() {
        try {
            HttpResponse<String> res = send(HttpRequest.newBuilder()
                    .uri(URI.create(props.getTradingBaseUrl() + "/v2/account"))
                    .GET());
            if (res.statusCode() / 100 != 2) {
                return null;
            }
            JsonNode n = readTree(res.body());
            return new AccountInfo(
                    n.path("status").asText(),
                    decimal(n, "cash"),
                    decimal(n, "buying_power"),
                    decimal(n, "equity"),
                    n.path("currency").asText("USD"));
        } catch (RuntimeException e) {
            log.debug("Alpaca account fetch failed: {}", e.getMessage());
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
            throw new IllegalStateException("Alpaca request failed: " + e.getMessage(), e);
        }
    }

    private JsonNode readTree(String body) {
        try {
            return json.readTree(body);
        } catch (Exception e) {
            throw new IllegalStateException("Unparseable Alpaca response: " + e.getMessage(), e);
        }
    }

    private AlpacaOrder parseOrder(JsonNode n) {
        return new AlpacaOrder(
                n.path("id").asText(),
                n.path("client_order_id").asText(),
                n.path("symbol").asText(),
                n.path("status").asText(),
                decimal(n, "filled_qty"),
                n.hasNonNull("filled_avg_price") ? new BigDecimal(n.path("filled_avg_price").asText()) : null);
    }

    private static BigDecimal decimal(JsonNode n, String field) {
        return n.hasNonNull(field) && !n.path(field).asText().isBlank()
                ? new BigDecimal(n.path(field).asText())
                : BigDecimal.ZERO;
    }
}
