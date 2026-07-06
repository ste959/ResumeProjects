package com.bonddesk.oms.fixedincome;

import com.bonddesk.oms.domain.OrderSide;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * A live request-for-quote: the client's request, the dealers' firm quotes, and the
 * lifecycle. Kept in memory (like a real RFQ, quotes are transient and expire in seconds);
 * the resulting trade is booked into the persistent order/position store on acceptance.
 */
public class Rfq {

    private final String id;
    private final String cusip;
    private final String description;
    private final String portfolio;
    private final String trader;
    private final OrderSide side;
    private final BigDecimal quantity;
    private final QuoteSet quotes;
    private final Instant createdAt;
    private final Instant expiresAt;

    private RfqStatus status = RfqStatus.QUOTED;
    private String acceptedDealer;
    private String executedOrderRef;

    public Rfq(String id, String cusip, String description, String portfolio, String trader,
               OrderSide side, BigDecimal quantity, QuoteSet quotes, Instant createdAt, Instant expiresAt) {
        this.id = id;
        this.cusip = cusip;
        this.description = description;
        this.portfolio = portfolio;
        this.trader = trader;
        this.side = side;
        this.quantity = quantity;
        this.quotes = quotes;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    public boolean isExpired(Instant now) {
        return now.isAfter(expiresAt);
    }

    public String getId() {
        return id;
    }

    public String getCusip() {
        return cusip;
    }

    public String getDescription() {
        return description;
    }

    public String getPortfolio() {
        return portfolio;
    }

    public String getTrader() {
        return trader;
    }

    public OrderSide getSide() {
        return side;
    }

    public BigDecimal getQuantity() {
        return quantity;
    }

    public QuoteSet getQuotes() {
        return quotes;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getExpiresAt() {
        return expiresAt;
    }

    public RfqStatus getStatus() {
        return status;
    }

    public void setStatus(RfqStatus status) {
        this.status = status;
    }

    public String getAcceptedDealer() {
        return acceptedDealer;
    }

    public void setAcceptedDealer(String acceptedDealer) {
        this.acceptedDealer = acceptedDealer;
    }

    public String getExecutedOrderRef() {
        return executedOrderRef;
    }

    public void setExecutedOrderRef(String executedOrderRef) {
        this.executedOrderRef = executedOrderRef;
    }
}
