package com.bonddesk.oms.idempotency;

import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;

/**
 * Multi-node idempotency store backed by Redis. The reserve is a single atomic {@code SET key val NX PX ttl}
 * — the same primitive every distributed idempotency/lock recipe uses — so across any number of OMS
 * instances exactly one request can acquire a given key. Active only when {@code oms.redis.enabled=true};
 * otherwise {@link InMemoryIdempotencyStore} backs the same interface.
 *
 * <p>The value encodes the state, the request fingerprint, and (once done) the result:
 * {@code R|<fingerprint>} while reserved, {@code D|<fingerprint>|<result>} once complete.
 */
public class RedisIdempotencyStore implements IdempotencyStore {

    private static final String RESERVED = "R";
    private static final String DONE = "D";
    private static final String SEP = "|";

    private final StringRedisTemplate redis;
    private final Duration ttl;

    public RedisIdempotencyStore(StringRedisTemplate redis, Duration ttl) {
        this.redis = redis;
        this.ttl = ttl;
    }

    private static String key(String idempotencyKey) {
        return "idem:" + idempotencyKey;
    }

    @Override
    public Reservation begin(String key, String fingerprint) {
        String k = key(key);
        Boolean acquired = redis.opsForValue()
                .setIfAbsent(k, RESERVED + SEP + fingerprint, ttl);   // SET NX PX
        if (Boolean.TRUE.equals(acquired)) {
            return new Reservation.Acquired();
        }
        String current = redis.opsForValue().get(k);
        if (current == null) {
            // Expired in the gap between SET NX and GET — rare; let the client retry the key.
            return new Reservation.InFlight();
        }
        String[] parts = current.split("\\" + SEP, 3);
        String state = parts[0];
        String storedFingerprint = parts.length > 1 ? parts[1] : "";
        if (!storedFingerprint.equals(fingerprint)) {
            return new Reservation.Mismatch();
        }
        if (DONE.equals(state)) {
            return new Reservation.Replay(parts.length > 2 ? parts[2] : "");
        }
        return new Reservation.InFlight();   // RESERVED by a concurrent request with the same body
    }

    @Override
    public void complete(String key, String result) {
        String k = key(key);
        String current = redis.opsForValue().get(k);
        String fingerprint = "";
        if (current != null) {
            String[] parts = current.split("\\" + SEP, 3);
            fingerprint = parts.length > 1 ? parts[1] : "";
        }
        // Keep the completed outcome discoverable for the TTL window so retries replay it.
        redis.opsForValue().set(k, DONE + SEP + fingerprint + SEP + result, ttl);
    }

    @Override
    public void release(String key) {
        String k = key(key);
        String current = redis.opsForValue().get(k);
        // Only drop our own reservation — never a completed outcome another retry may still replay.
        if (current != null && current.startsWith(RESERVED + SEP)) {
            redis.delete(k);
        }
    }
}
