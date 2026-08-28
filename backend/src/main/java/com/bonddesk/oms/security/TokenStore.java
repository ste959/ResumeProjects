package com.bonddesk.oms.security;

import java.time.Duration;
import java.util.List;

/**
 * Server-side token lifecycle state — the part of the identity layer that a stateless JWT cannot hold on
 * its own: refresh tokens (so an access token can stay short-lived) and revocation.
 *
 * <p><b>Refresh tokens</b> are opaque, single-use, and rotating: each successful refresh mints a new one
 * and invalidates the old. All refresh tokens minted from one login share a <em>family</em>; if an
 * already-rotated token is ever presented again — the signature of a stolen, replayed token — the whole
 * family is revoked ({@link RefreshOutcome.Reused}), so a theft can't outlive its detection. Tokens are
 * stored hashed, never in the clear.
 *
 * <p><b>Access-token revocation</b> is a short-lived {@code jti} denylist: logout adds the current token's
 * id, and the auth filter rejects it for the token's remaining lifetime.
 *
 * <p>Two implementations back this — {@link InMemoryTokenStore} (single node, default) and
 * {@link RedisTokenStore} (shared across instances) — selected the same way as the idempotency store.
 */
public interface TokenStore {

    /** Mint the first refresh token of a new family for a user. Returns the raw token (shown once). */
    String issueRefresh(String username, List<String> roles, Duration ttl);

    /** Atomically rotate a refresh token: invalidate it and mint its successor, or report the failure. */
    RefreshOutcome rotateRefresh(String rawToken, Duration ttl);

    /** Revoke the whole family a refresh token belongs to (logout). No-op if the token is unknown. */
    void revokeRefreshFamily(String rawToken);

    /** Deny an access token by its {@code jti} for {@code ttl} (its remaining lifetime). */
    void revokeAccess(String jti, Duration ttl);

    boolean isAccessRevoked(String jti);

    sealed interface RefreshOutcome permits RefreshOutcome.Rotated, RefreshOutcome.Invalid, RefreshOutcome.Reused {

        /** Success: the old token is now dead; {@code newRefreshToken} replaces it for the same identity. */
        record Rotated(String newRefreshToken, String username, List<String> roles) implements RefreshOutcome {}

        /** The token is unknown or expired. */
        record Invalid() implements RefreshOutcome {}

        /** The token was already rotated out — a replay; its family has been revoked. */
        record Reused() implements RefreshOutcome {}
    }
}
