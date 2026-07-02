package com.bonddesk.oms.domain;

/** How long an order remains active before it expires. */
public enum TimeInForce {
    /** Good for the trading day. */
    DAY,
    /** Good till cancelled. */
    GTC,
    /** Immediate-or-cancel: fill what you can now, cancel the rest. */
    IOC,
    /** Fill-or-kill: fill the entire quantity now or cancel completely. */
    FOK
}
