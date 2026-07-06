package com.bonddesk.oms.domain;

/**
 * The asset class of a tradable security. This is the dimension that lets one order and
 * position model span multiple markets: each class is executed through the market
 * structure it actually has in the real world. Fixed income trades over-the-counter via
 * dealer request-for-quote (RFQ); equities trade on a lit central limit order book, which
 * this platform routes to an external broker.
 */
public enum AssetClass {

    /** Bonds — priced from a yield curve, executed via dealer RFQ. */
    FIXED_INCOME,

    /** Listed shares — quoted in currency per share, executed on a lit order book. */
    EQUITY
}
