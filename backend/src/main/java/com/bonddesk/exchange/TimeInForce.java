package com.bonddesk.exchange;

/**
 * Time-in-force semantics for the unfilled part of an order:
 * <ul>
 *   <li>{@code GTC} — good-till-cancelled: rest any remainder (LIMIT only).</li>
 *   <li>{@code IOC} — immediate-or-cancel: fill what's marketable now, cancel the rest.</li>
 *   <li>{@code FOK} — fill-or-kill: fill in full immediately or reject entirely (no partial).</li>
 * </ul>
 */
public enum TimeInForce {
    GTC,
    IOC,
    FOK
}
