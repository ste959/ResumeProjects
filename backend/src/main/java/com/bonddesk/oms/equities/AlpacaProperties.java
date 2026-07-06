package com.bonddesk.oms.equities;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

/**
 * Configuration for the Alpaca equities integration: a real market-data feed (IEX) and
 * routing to Alpaca's <em>paper</em> trading broker for execution.
 *
 * <p>The API key/secret are read from the environment (or an optional, git-ignored
 * {@code alpaca-local.yml}) and default to blank, so the application boots without
 * credentials — the feed simply stays idle, exactly as the crypto feed does when disabled.
 */
@ConfigurationProperties(prefix = "oms.equities")
public class AlpacaProperties {

    /** Master switch for the equities module. */
    private boolean enabled = true;

    /** Alpaca API key id (paper account). Blank = module idle. */
    private String keyId = "";

    /** Alpaca API secret key (paper account). Blank = module idle. */
    private String secretKey = "";

    /** Market-data websocket. Free accounts use the IEX feed. */
    private String dataWsUrl = "wss://stream.data.alpaca.markets/v2/iex";

    /** Paper trading REST base. Live trading would be https://api.alpaca.markets. */
    private String tradingBaseUrl = "https://paper-api.alpaca.markets";

    /** Symbols to stream and trade. */
    private List<String> symbols = List.of("AAPL", "MSFT", "NVDA", "AMZN", "JPM", "TSLA");

    /** Trade prints retained per symbol for the tape. */
    private int tradeTapeSize = 50;

    /** How often the broker reconciler polls Alpaca for fills, in milliseconds. */
    private long reconcileMs = 2000;

    /** True only when both credentials are present. */
    public boolean hasCredentials() {
        return keyId != null && !keyId.isBlank() && secretKey != null && !secretKey.isBlank();
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getKeyId() {
        return keyId;
    }

    public void setKeyId(String keyId) {
        this.keyId = keyId;
    }

    public String getSecretKey() {
        return secretKey;
    }

    public void setSecretKey(String secretKey) {
        this.secretKey = secretKey;
    }

    public String getDataWsUrl() {
        return dataWsUrl;
    }

    public void setDataWsUrl(String dataWsUrl) {
        this.dataWsUrl = dataWsUrl;
    }

    public String getTradingBaseUrl() {
        return tradingBaseUrl;
    }

    public void setTradingBaseUrl(String tradingBaseUrl) {
        this.tradingBaseUrl = tradingBaseUrl;
    }

    public List<String> getSymbols() {
        return symbols;
    }

    public void setSymbols(List<String> symbols) {
        this.symbols = symbols;
    }

    public int getTradeTapeSize() {
        return tradeTapeSize;
    }

    public void setTradeTapeSize(int tradeTapeSize) {
        this.tradeTapeSize = tradeTapeSize;
    }

    public long getReconcileMs() {
        return reconcileMs;
    }

    public void setReconcileMs(long reconcileMs) {
        this.reconcileMs = reconcileMs;
    }
}
