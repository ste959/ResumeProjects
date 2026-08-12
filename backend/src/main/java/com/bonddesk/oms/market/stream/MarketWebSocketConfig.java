package com.bonddesk.oms.market.stream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * Registers the live market-data WebSocket at {@code /ws/market}. Origins are bound to the REST CORS
 * allow-list ({@code oms.cors.allowed-origins}) — localhost for dev; the nginx/Vite proxy makes it
 * same-origin in the compose stack. Gated with the crypto feed so the whole push path is inert when
 * the feed is disabled.
 */
@Configuration
@EnableWebSocket
@ConditionalOnProperty(name = "oms.crypto.enabled", matchIfMissing = true)
public class MarketWebSocketConfig implements WebSocketConfigurer {

    private final MarketSocketHandler handler;
    private final String[] allowedOrigins;

    public MarketWebSocketConfig(MarketSocketHandler handler,
                                 @Value("${oms.cors.allowed-origins:http://localhost:*}") String allowedOrigins) {
        this.handler = handler;
        this.allowedOrigins = allowedOrigins.split("\\s*,\\s*");
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/market").setAllowedOriginPatterns(allowedOrigins);
    }
}
