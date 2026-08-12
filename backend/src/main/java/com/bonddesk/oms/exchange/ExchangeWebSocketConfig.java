package com.bonddesk.oms.exchange;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/** Registers the live exchange market-data WebSocket at {@code /ws/exchange}. */
@Configuration
@EnableWebSocket
public class ExchangeWebSocketConfig implements WebSocketConfigurer {

    private final ExchangeSocketHandler handler;
    // Bound to the same origin allow-list as REST CORS (oms.cors.allowed-origins). WebSockets bypass
    // the browser CORS check, so an unrestricted "*" here invites cross-site WebSocket hijacking.
    private final String[] allowedOrigins;

    public ExchangeWebSocketConfig(ExchangeSocketHandler handler,
                                   @Value("${oms.cors.allowed-origins:http://localhost:*}") String allowedOrigins) {
        this.handler = handler;
        this.allowedOrigins = allowedOrigins.split("\\s*,\\s*");
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/exchange").setAllowedOriginPatterns(allowedOrigins);
    }
}
