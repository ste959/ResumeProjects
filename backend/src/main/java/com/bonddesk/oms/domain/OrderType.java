package com.bonddesk.oms.domain;

/** Execution instruction for an order. */
public enum OrderType {
    /** Execute immediately at the prevailing market price. */
    MARKET,
    /** Execute only at the limit price or better. */
    LIMIT
}
