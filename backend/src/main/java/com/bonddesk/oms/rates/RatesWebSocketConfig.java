package com.bonddesk.oms.rates;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * Registers the live rates-desk WebSocket at {@code /ws/rates}. WebSocket support is already enabled
 * by the exchange config (@EnableWebSocket); Spring collects every WebSocketConfigurer bean, so this
 * just adds its handler. Origins are bound to the REST CORS allow-list ({@code oms.cors.allowed-origins}).
 */
@Configuration
public class RatesWebSocketConfig implements WebSocketConfigurer {

    private final RatesSocketHandler handler;
    private final String[] allowedOrigins;

    public RatesWebSocketConfig(RatesSocketHandler handler,
                                @Value("${oms.cors.allowed-origins:http://localhost:*}") String allowedOrigins) {
        this.handler = handler;
        this.allowedOrigins = allowedOrigins.split("\\s*,\\s*");
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/rates").setAllowedOriginPatterns(allowedOrigins);
    }
}
