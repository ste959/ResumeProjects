package com.bonddesk.oms.fixedincome;

/** Lifecycle of a request-for-quote: quotes are firm until accepted or they expire. */
public enum RfqStatus {
    QUOTED,
    EXECUTED,
    EXPIRED
}
