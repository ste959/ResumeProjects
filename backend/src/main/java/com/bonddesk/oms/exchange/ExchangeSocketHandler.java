package com.bonddesk.oms.exchange;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Pushes the live exchange market-data snapshot to connected browsers over {@code /ws/exchange}. A
 * new client immediately gets the latest snapshot so the book renders on connect; thereafter the
 * simulation broadcasts a fresh snapshot each tick.
 */
@Component
public class ExchangeSocketHandler extends TextWebSocketHandler {

    private final Set<WebSocketSession> sessions = ConcurrentHashMap.newKeySet();
    private volatile String latest;

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        sessions.add(session);
        String snap = latest;
        if (snap != null) {
            session.sendMessage(new TextMessage(snap));
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session);
    }

    /** Broadcast a snapshot to every subscriber (and remember it for the next client to connect). */
    public void broadcast(String json) {
        latest = json;
        for (WebSocketSession session : sessions) {
            try {
                synchronized (session) {
                    if (session.isOpen()) {
                        session.sendMessage(new TextMessage(json));
                    }
                }
            } catch (Exception e) {
                sessions.remove(session);
            }
        }
    }
}
