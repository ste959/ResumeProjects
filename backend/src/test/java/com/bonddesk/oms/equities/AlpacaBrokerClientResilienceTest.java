package com.bonddesk.oms.equities;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.domain.TimeInForce;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.retry.RetryConfig;
import io.github.resilience4j.retry.RetryRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * The resilience contract around the Alpaca venue client, exercised end-to-end against a real local HTTP
 * server (no Docker): transient failures (5xx/IO) are retried and trip the breaker, while a terminal 4xx
 * rejection is neither retried nor counted. This is the distinction that keeps a busy order path from
 * hammering a briefly-flaky broker without also blinding the breaker to genuine outages.
 */
class AlpacaBrokerClientResilienceTest {

    private HttpServer server;
    private final AtomicInteger hits = new AtomicInteger();
    // Scripted HTTP statuses, consumed one per request; once drained, `fallbackStatus` is returned.
    private final ConcurrentLinkedQueue<Integer> statusScript = new ConcurrentLinkedQueue<>();
    private volatile int fallbackStatus = 200;

    private AlpacaBrokerClient client;
    private CircuitBreaker breaker;

    @BeforeEach
    void setUp() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();

        AlpacaProperties props = new AlpacaProperties();
        props.setKeyId("test-key");
        props.setSecretKey("test-secret");
        props.setTradingBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());

        // Small, fast policies for the test — same shape as application.yml, tuned so the window fills and
        // the retry backoff elapses quickly. Registries seed "alpaca" from these as their default config.
        RetryRegistry retries = RetryRegistry.of(RetryConfig.custom()
                .maxAttempts(3)
                .waitDuration(Duration.ofMillis(10))
                .retryExceptions(BrokerUnavailableException.class)
                .ignoreExceptions(BrokerRejectedException.class)
                .build());
        CircuitBreakerRegistry breakers = CircuitBreakerRegistry.of(CircuitBreakerConfig.custom()
                .slidingWindowType(SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50f)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .recordExceptions(BrokerUnavailableException.class)
                .ignoreExceptions(BrokerRejectedException.class)
                .build());

        client = new AlpacaBrokerClient(props, new ObjectMapper(), breakers, retries);
        breaker = breakers.circuitBreaker("alpaca");
    }

    @AfterEach
    void tearDown() {
        server.stop(0);
    }

    @Test
    void lookupSucceedsWithoutRetryOnHappyPath() {
        statusScript.add(200);
        AlpacaBrokerClient.AlpacaOrder order = client.getByClientOrderId("ref-1");
        assertThat(order).isNotNull();
        assertThat(hits.get()).isEqualTo(1);
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
    }

    @Test
    void transientFailuresAreRetriedThenSucceed() {
        statusScript.add(503);
        statusScript.add(503);
        statusScript.add(200);
        AlpacaBrokerClient.AlpacaOrder order = client.getByClientOrderId("ref-1");
        assertThat(order).isNotNull();
        assertThat(hits.get()).isEqualTo(3);   // two failed attempts, then the recovery
    }

    @Test
    void notFoundIsNullNotAnError() {
        statusScript.add(404);
        assertThat(client.getByClientOrderId("missing")).isNull();
        assertThat(hits.get()).isEqualTo(1);
    }

    @Test
    void clientRejectionIsTerminalNotRetriedAndDoesNotTripTheBreaker() {
        statusScript.add(400);
        assertThatThrownBy(() -> client.getByClientOrderId("bad"))
                .isInstanceOf(BrokerRejectedException.class);
        assertThat(hits.get()).isEqualTo(1);    // a 4xx is not retried
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
    }

    @Test
    void submitParsesTheBrokerOrderOnSuccess() {
        statusScript.add(200);
        assertThat(client.submit(sampleOrder())).isNotNull();
        assertThat(hits.get()).isEqualTo(1);
    }

    @Test
    void submitRejectionSurfacesAsTerminalRejection() {
        statusScript.add(422);
        assertThatThrownBy(() -> client.submit(sampleOrder()))
                .isInstanceOf(BrokerRejectedException.class);
        assertThat(hits.get()).isEqualTo(1);
    }

    @Test
    void breakerOpensUnderSustainedOutageAndThenFailsFast() {
        fallbackStatus = 503;   // every request 5xxs — a broker outage

        // Drive calls until the breaker trips. Each call retries internally, so the window fills quickly.
        for (int i = 0; i < 6 && breaker.getState() == CircuitBreaker.State.CLOSED; i++) {
            assertThatThrownBy(() -> client.getByClientOrderId("ref"))
                    .isInstanceOf(BrokerUnavailableException.class);
        }
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // Once open, the next call must fail fast — no network round-trip to the down venue.
        int hitsBeforeOpenCall = hits.get();
        assertThatThrownBy(() -> client.getByClientOrderId("ref"))
                .isInstanceOf(BrokerUnavailableException.class);
        assertThat(hits.get()).isEqualTo(hitsBeforeOpenCall);
    }

    private Order sampleOrder() {
        Security sec = mock(Security.class);
        when(sec.getTicker()).thenReturn("AAPL");
        Order order = mock(Order.class);
        when(order.getSecurity()).thenReturn(sec);
        when(order.getQuantity()).thenReturn(new BigDecimal("10"));
        when(order.getSide()).thenReturn(OrderSide.BUY);
        when(order.getOrderType()).thenReturn(OrderType.MARKET);
        when(order.getTimeInForce()).thenReturn(TimeInForce.DAY);
        when(order.getOrderRef()).thenReturn("ref-1");
        return order;
    }

    private void handle(HttpExchange exchange) throws IOException {
        hits.incrementAndGet();
        Integer scripted = statusScript.poll();
        int status = scripted != null ? scripted : fallbackStatus;
        String body = status / 100 == 2
                ? "{\"id\":\"brk-1\",\"client_order_id\":\"ref-1\",\"symbol\":\"AAPL\",\"status\":\"accepted\"}"
                : "{\"message\":\"status " + status + "\"}";
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }
}
