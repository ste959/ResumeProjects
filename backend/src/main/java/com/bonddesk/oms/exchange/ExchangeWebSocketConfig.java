package com.bonddesk.oms.exchange;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/** Registers the live exchange market-data WebSocket at {@code /ws/exchange}. */
@Configuration
@EnableWebSocket
public class ExchangeWebSocketConfig implements WebSocketConfigurer {

    private final ExchangeSocketHandler handler;

    public ExchangeWebSocketConfig(ExchangeSocketHandler handler) {
        this.handler = handler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/exchange").setAllowedOriginPatterns("*");
    }
}
