package com.bonddesk.oms.market;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

/**
 * Configuration for the live Coinbase market-data feed. Bound from {@code oms.crypto.*}.
 * Market data on Coinbase's Advanced Trade {@code level2} channel is public — no API key.
 */
@ConfigurationProperties(prefix = "oms.crypto")
public class CoinbaseProperties {

    /** Master switch for the live feed (off in tests / offline environments). */
    private boolean enabled = true;

    private String wsUrl = "wss://advanced-trade-ws.coinbase.com";

    /** Products to subscribe to (Coinbase product ids). */
    private List<String> products = List.of("BTC-USD", "ETH-USD", "SOL-USD");

    /** How many recent trade prints to retain per product for the tape. */
    private int tradeTapeSize = 50;

    /** Capture a per-second microstructure snapshot to CSV for offline research. */
    private boolean recorderEnabled = true;

    /** Directory the recorder writes to (gitignored). */
    private String recorderDir = "market-data";

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }

    public String getWsUrl() { return wsUrl; }
    public void setWsUrl(String wsUrl) { this.wsUrl = wsUrl; }

    public List<String> getProducts() { return products; }
    public void setProducts(List<String> products) { this.products = products; }

    public int getTradeTapeSize() { return tradeTapeSize; }
    public void setTradeTapeSize(int tradeTapeSize) { this.tradeTapeSize = tradeTapeSize; }

    public boolean isRecorderEnabled() { return recorderEnabled; }
    public void setRecorderEnabled(boolean recorderEnabled) { this.recorderEnabled = recorderEnabled; }

    public String getRecorderDir() { return recorderDir; }
    public void setRecorderDir(String recorderDir) { this.recorderDir = recorderDir; }
}

