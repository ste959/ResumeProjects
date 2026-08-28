package com.bonddesk.oms.security;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

/**
 * Single-node {@link TokenStore} backed by concurrent maps — the default when Redis is off, and enough
 * for one instance and every test. Refresh tokens are stored under the SHA-256 of the raw token (so a
 * store dump never yields a usable token), and the rotate/revoke transitions are guarded by a lock so a
 * concurrent replay of a rotated token is reliably caught as reuse.
 */
public class InMemoryTokenStore implements TokenStore {

    private record Rec(String username, List<String> roles, String familyId, long expiresAt, boolean used) {}

    private final Map<String, Rec> refresh = new ConcurrentHashMap<>();   // sha256(rawToken) -> record
    private final Map<String, Long> revokedJti = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();
    private final LongSupplier nowMillis;

    public InMemoryTokenStore() {
        this(System::currentTimeMillis);
    }

    InMemoryTokenStore(LongSupplier nowMillis) {
        this.nowMillis = nowMillis;
    }

    @Override
    public synchronized String issueRefresh(String username, List<String> roles, Duration ttl) {
        pruneExpired();   // bound growth: drop lapsed refresh + revocation entries on each new login
        return mint(username, roles, newFamilyId(), ttl);
    }

    @Override
    public synchronized RefreshOutcome rotateRefresh(String rawToken, Duration ttl) {
        String hash = sha256(rawToken);
        Rec rec = refresh.get(hash);
        long now = nowMillis.getAsLong();
        if (rec == null || rec.expiresAt() <= now) {
            return new RefreshOutcome.Invalid();
        }
        if (rec.used()) {
            // A rotated-out token presented again => replay of a leaked token. Burn the whole family.
            revokeFamily(rec.familyId());
            return new RefreshOutcome.Reused();
        }
        refresh.put(hash, new Rec(rec.username(), rec.roles(), rec.familyId(), rec.expiresAt(), true));
        String next = mint(rec.username(), rec.roles(), rec.familyId(), ttl);
        return new RefreshOutcome.Rotated(next, rec.username(), rec.roles());
    }

    @Override
    public synchronized void revokeRefreshFamily(String rawToken) {
        Rec rec = refresh.get(sha256(rawToken));
        if (rec != null) {
            revokeFamily(rec.familyId());
        }
    }

    @Override
    public void revokeAccess(String jti, Duration ttl) {
        revokedJti.put(jti, nowMillis.getAsLong() + ttl.toMillis());
    }

    @Override
    public boolean isAccessRevoked(String jti) {
        Long until = revokedJti.get(jti);
        if (until == null) {
            return false;
        }
        if (until <= nowMillis.getAsLong()) {
            revokedJti.remove(jti);   // lazy expiry
            return false;
        }
        return true;
    }

    private String mint(String username, List<String> roles, String familyId, Duration ttl) {
        String raw = randomToken();
        refresh.put(sha256(raw), new Rec(username, roles, familyId, nowMillis.getAsLong() + ttl.toMillis(), false));
        return raw;
    }

    private void revokeFamily(String familyId) {
        refresh.entrySet().removeIf(e -> e.getValue().familyId().equals(familyId));
    }

    /** Drop refresh records and denylist entries that have passed their expiry, so neither map grows
     *  without bound over a long-running process. Called under the instance lock. */
    private void pruneExpired() {
        long now = nowMillis.getAsLong();
        refresh.values().removeIf(rec -> rec.expiresAt() <= now);
        revokedJti.values().removeIf(expiresAt -> expiresAt <= now);
    }

    /** Test-only: number of refresh records currently retained. */
    int refreshEntryCount() {
        return refresh.size();
    }

    private String newFamilyId() {
        return randomToken();
    }

    private String randomToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes()));
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
