package com.bonddesk.exchange;

import java.util.List;

/** Fans engine events out to several listeners (e.g. the market maker, the feed, and analytics). */
public final class CompositeListener implements ExchangeListener {

    private final List<ExchangeListener> listeners;

    public CompositeListener(List<ExchangeListener> listeners) {
        this.listeners = listeners;
    }

    @Override public void onAccepted(Order o) { for (var l : listeners) l.onAccepted(o); }
    @Override public void onRejected(long id, String p, String r) { for (var l : listeners) l.onRejected(id, p, r); }
    @Override public void onResting(Order o) { for (var l : listeners) l.onResting(o); }
    @Override public void onTrade(Trade t) { for (var l : listeners) l.onTrade(t); }
    @Override public void onCancelled(Order o) { for (var l : listeners) l.onCancelled(o); }
}
