package com.bonddesk.oms.idempotency;

import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

/**
 * Single-node idempotency store backed by a {@link ConcurrentHashMap}. The default when Redis is off —
 * correct for one instance, and enough for the demo and every test. State transitions use
 * {@link ConcurrentHashMap#compute} so a reserve is atomic per key even under concurrent retries.
 *
 * <p>Entries expire after a TTL (lazily, on the next touch of the key) so the map can't grow without
 * bound; the clock is injectable so expiry is deterministic in tests.
 */
public class InMemoryIdempotencyStore implements IdempotencyStore {

    private enum State { RESERVED, COMPLETED }

    private record Entry(State state, String fingerprint, String result, long expiresAtMillis) {}

    private final ConcurrentHashMap<String, Entry> entries = new ConcurrentHashMap<>();
    private final long ttlMillis;
    private final LongSupplier nowMillis;

    public InMemoryIdempotencyStore(long ttlMillis) {
        this(ttlMillis, System::currentTimeMillis);
    }

    InMemoryIdempotencyStore(long ttlMillis, LongSupplier nowMillis) {
        this.ttlMillis = ttlMillis;
        this.nowMillis = nowMillis;
    }

    @Override
    public Reservation begin(String key, String fingerprint) {
        long now = nowMillis.getAsLong();
        boolean[] acquired = {false};
        // compute() runs atomically for the key, so two racing retries can't both acquire it: exactly one
        // call replaces a missing/expired entry and sets acquired[0]; the other observes the reservation.
        Entry entry = entries.compute(key, (k, existing) -> {
            if (existing != null && existing.expiresAtMillis() > now) {
                return existing;                 // a still-valid entry belongs to an earlier call
            }
            acquired[0] = true;
            return new Entry(State.RESERVED, fingerprint, null, now + ttlMillis);
        });

        if (!entry.fingerprint().equals(fingerprint)) {
            return new Reservation.Mismatch();   // same key, different request body
        }
        if (entry.state() == State.COMPLETED) {
            return new Reservation.Replay(entry.result());
        }
        return acquired[0] ? new Reservation.Acquired() : new Reservation.InFlight();
    }

    @Override
    public void complete(String key, String result) {
        long now = nowMillis.getAsLong();
        entries.compute(key, (k, existing) -> {
            String fp = existing != null ? existing.fingerprint() : "";
            return new Entry(State.COMPLETED, fp, result, now + ttlMillis);
        });
    }

    @Override
    public void release(String key) {
        entries.computeIfPresent(key, (k, existing) ->
                existing.state() == State.RESERVED ? null : existing);
    }
}
