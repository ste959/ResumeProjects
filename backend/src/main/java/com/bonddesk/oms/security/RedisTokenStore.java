package com.bonddesk.oms.security;

import org.springframework.data.redis.core.StringRedisTemplate;

import java.security.SecureRandom;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;

/**
 * Multi-node {@link TokenStore} backed by Redis, so refresh/revocation state is shared across every OMS
 * instance. Refresh records live at {@code oms:rt:<sha256>} with a TTL, a per-family set at
 * {@code oms:rtf:<family>} lets logout / reuse-detection revoke a whole family, and denied access-token
 * ids live at {@code oms:rjti:<jti>} for their remaining lifetime. Tokens are stored hashed.
 *
 * <p>The rotate step is read-then-write rather than a single atomic op; a production multi-writer setup
 * would fold it into a Lua script so a concurrent replay is impossible rather than merely unlikely.
 */
public class RedisTokenStore implements TokenStore {

    private static final char SEP = '\u0001';   // a delimiter that can't appear in a username or role name

    private final StringRedisTemplate redis;
    private final SecureRandom random = new SecureRandom();

    public RedisTokenStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public String issueRefresh(String username, List<String> roles, Duration ttl) {
        return mint(username, roles, randomToken(), ttl);
    }

    @Override
    public RefreshOutcome rotateRefresh(String rawToken, Duration ttl) {
        String hash = InMemoryTokenStore.sha256(rawToken);
        String value = redis.opsForValue().get(key(hash));
        if (value == null) {
            return new RefreshOutcome.Invalid();
        }
        String[] parts = value.split(String.valueOf(SEP), -1);
        String username = parts[0];
        List<String> roles = parts[1].isEmpty() ? List.of() : List.of(parts[1].split(","));
        String familyId = parts[2];
        boolean used = "1".equals(parts[3]);
        if (used) {
            revokeFamily(familyId);
            return new RefreshOutcome.Reused();
        }
        redis.opsForValue().set(key(hash), encode(username, roles, familyId, true), ttl);   // mark used
        String next = mint(username, roles, familyId, ttl);
        return new RefreshOutcome.Rotated(next, username, roles);
    }

    @Override
    public void revokeRefreshFamily(String rawToken) {
        String value = redis.opsForValue().get(key(InMemoryTokenStore.sha256(rawToken)));
        if (value != null) {
            revokeFamily(value.split(String.valueOf(SEP), -1)[2]);
        }
    }

    @Override
    public void revokeAccess(String jti, Duration ttl) {
        redis.opsForValue().set(jtiKey(jti), "1", ttl);
    }

    @Override
    public boolean isAccessRevoked(String jti) {
        return Boolean.TRUE.equals(redis.hasKey(jtiKey(jti)));
    }

    private String mint(String username, List<String> roles, String familyId, Duration ttl) {
        String raw = randomToken();
        String hash = InMemoryTokenStore.sha256(raw);
        redis.opsForValue().set(key(hash), encode(username, roles, familyId, false), ttl);
        redis.opsForSet().add(famKey(familyId), hash);
        redis.expire(famKey(familyId), ttl);
        return raw;
    }

    private void revokeFamily(String familyId) {
        Set<String> members = redis.opsForSet().members(famKey(familyId));
        if (members != null) {
            members.forEach(h -> redis.delete(key(h)));
        }
        redis.delete(famKey(familyId));
    }

    private static String encode(String username, List<String> roles, String familyId, boolean used) {
        return username + SEP + String.join(",", roles) + SEP + familyId + SEP + (used ? "1" : "0");
    }

    private static String key(String hash) {
        return "oms:rt:" + hash;
    }

    private static String famKey(String familyId) {
        return "oms:rtf:" + familyId;
    }

    private static String jtiKey(String jti) {
        return "oms:rjti:" + jti;
    }

    private String randomToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }
}
