package com.bonddesk.oms.market.stream;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * Registers the live market-data WebSocket at {@code /ws/market}. Origins are permitted by pattern
 * (localhost for dev; the nginx/Vite proxy makes it same-origin in the compose stack) — lock these
 * down for a real deployment, as with the REST CORS config. Gated with the crypto feed so the whole
 * push path is inert when the feed is disabled.
 */
@Configuration
@EnableWebSocket
@ConditionalOnProperty(name = "oms.crypto.enabled", matchIfMissing = true)
public class MarketWebSocketConfig implements WebSocketConfigurer {

    private final MarketSocketHandler handler;

    public MarketWebSocketConfig(MarketSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/market").setAllowedOriginPatterns("*");
    }
}
