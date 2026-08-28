package com.bonddesk.oms.security;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

import java.security.SecureRandom;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Multi-node {@link TokenStore} backed by Redis, so refresh/revocation state is shared across every OMS
 * instance. Each refresh token is a hash at {@code oms:rt:<sha256>} (fields user/roles/fam/used) with a
 * TTL; a per-family set at {@code oms:rtf:<family>} lets logout / reuse-detection revoke a whole family;
 * denied access-token ids live at {@code oms:rjti:<jti>} for their remaining lifetime. Tokens are stored
 * hashed, never in the clear.
 *
 * <p>The rotate step is a single atomic <b>Lua CAS</b> ({@link #ROTATE}): it checks and flips the
 * {@code used} flag in one server-side operation, so two concurrent replays of the same token can never
 * both succeed — exactly one flips {@code 0 -> 1}; a second sees {@code used == 1} and the family is burned.
 * (The in-memory store, {@link InMemoryTokenStore}, is the behavioral reference exercised in unit tests;
 * this Redis path is exercised wherever a real Redis is present.)
 */
public class RedisTokenStore implements TokenStore {

    // Atomic rotate: EXISTS? -> INVALID; used==1 -> revoke family + REUSED; else set used=1 and return the record.
    // ARGV[1] = family-key prefix, ARGV[2] = refresh-key prefix.
    private static final RedisScript<String> ROTATE = new DefaultRedisScript<>("""
            if redis.call('EXISTS', KEYS[1]) == 0 then return 'INVALID' end
            if redis.call('HGET', KEYS[1], 'used') == '1' then
              local fam = redis.call('HGET', KEYS[1], 'fam')
              local famKey = ARGV[1] .. fam
              local members = redis.call('SMEMBERS', famKey)
              for i = 1, #members do redis.call('DEL', ARGV[2] .. members[i]) end
              redis.call('DEL', famKey)
              return 'REUSED'
            end
            redis.call('HSET', KEYS[1], 'used', '1')
            return redis.call('HGET', KEYS[1], 'user') .. '|'
                .. redis.call('HGET', KEYS[1], 'roles') .. '|'
                .. redis.call('HGET', KEYS[1], 'fam')
            """, String.class);

    private static final String REFRESH_PREFIX = "oms:rt:";
    private static final String FAMILY_PREFIX = "oms:rtf:";

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
        String result = redis.execute(ROTATE, List.of(key(InMemoryTokenStore.sha256(rawToken))),
                FAMILY_PREFIX, REFRESH_PREFIX);
        if (result == null || result.equals("INVALID")) {
            return new RefreshOutcome.Invalid();
        }
        if (result.equals("REUSED")) {
            return new RefreshOutcome.Reused();
        }
        String[] parts = result.split("\\|", 3);
        String username = parts[0];
        List<String> roles = parts[1].isEmpty() ? List.of() : List.of(parts[1].split(","));
        String next = mint(username, roles, parts[2], ttl);
        return new RefreshOutcome.Rotated(next, username, roles);
    }

    @Override
    public void revokeRefreshFamily(String rawToken) {
        Object fam = redis.opsForHash().get(key(InMemoryTokenStore.sha256(rawToken)), "fam");
        if (fam != null) {
            revokeFamily(fam.toString());
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
        String k = key(hash);
        redis.opsForHash().putAll(k, Map.of(
                "user", username, "roles", String.join(",", roles), "fam", familyId, "used", "0"));
        redis.expire(k, ttl);
        redis.opsForSet().add(FAMILY_PREFIX + familyId, hash);
        redis.expire(FAMILY_PREFIX + familyId, ttl);
        return raw;
    }

    private void revokeFamily(String familyId) {
        Set<String> members = redis.opsForSet().members(FAMILY_PREFIX + familyId);
        if (members != null) {
            members.forEach(h -> redis.delete(key(h)));
        }
        redis.delete(FAMILY_PREFIX + familyId);
    }

    private static String key(String hash) {
        return REFRESH_PREFIX + hash;
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
