package com.bonddesk.oms.rates;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * Registers the live rates-desk WebSocket at {@code /ws/rates}. WebSocket support is already enabled
 * by the exchange config (@EnableWebSocket); Spring collects every WebSocketConfigurer bean, so this
 * just adds its handler.
 */
@Configuration
public class RatesWebSocketConfig implements WebSocketConfigurer {

    private final RatesSocketHandler handler;

    public RatesWebSocketConfig(RatesSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/rates").setAllowedOriginPatterns("*");
    }
}
