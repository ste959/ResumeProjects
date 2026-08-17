package com.bonddesk.oms.domain;

/**
 * Access roles. {@code SERVICE} is the machine/automation role granted by a valid API key (see
 * {@code ApiKeyAuthFilter}); the others are human roles carried in a login-issued JWT.
 */
public enum Role {
    VIEWER,   // read-only
    TRADER,   // may place/route/cancel orders
    ADMIN,    // may also run privileged actions (rebalance, restricted lists)
    SERVICE   // non-interactive automation (API key)
}
