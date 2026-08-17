package com.bonddesk.oms.idempotency;

/**
 * A store for API idempotency keys: it lets a mutating endpoint make a client's retry safe. A client
 * sends the same {@code Idempotency-Key} on a retry; the first request does the work and records its
 * outcome, and any replay returns that same outcome instead of acting twice.
 *
 * <p>Each key is bound to a <em>request fingerprint</em> (a hash of the request body), so reusing a key
 * with a <em>different</em> body is caught as a client mistake rather than silently returning the wrong
 * resource. The three states a {@link #begin} can report:
 * <ul>
 *   <li>{@link Reservation.Acquired} — first time seen: the caller owns the key and must do the work,
 *       then call {@link #complete} (or {@link #release} if it fails).</li>
 *   <li>{@link Reservation.InFlight} — a concurrent request with the same key+fingerprint is still
 *       working; the caller should back off (HTTP 409).</li>
 *   <li>{@link Reservation.Replay} — the work already completed; the caller returns the recorded result.</li>
 *   <li>{@link Reservation.Mismatch} — the key was seen with a different fingerprint (HTTP 422).</li>
 * </ul>
 *
 * <p>Two implementations back this: {@link InMemoryIdempotencyStore} (default, single-node) and a
 * Redis-backed store (multi-node, activated by {@code oms.redis.enabled=true}).
 */
public interface IdempotencyStore {

    /** Atomically reserve {@code key} for {@code fingerprint}, or report the state already recorded. */
    Reservation begin(String key, String fingerprint);

    /** Record the successful outcome for a key this caller {@link Reservation.Acquired reserved}. */
    void complete(String key, String result);

    /** Drop a reservation the caller could not complete, so the client may retry the same key. */
    void release(String key);

    sealed interface Reservation
            permits Reservation.Acquired, Reservation.InFlight, Reservation.Replay, Reservation.Mismatch {

        /** First time this key was seen — the caller owns it and must do the work. */
        record Acquired() implements Reservation {}

        /** A concurrent request with the same key is still processing. */
        record InFlight() implements Reservation {}

        /** The work already completed; {@code result} is the recorded outcome (an order reference). */
        record Replay(String result) implements Reservation {}

        /** The key was previously used with a different request body. */
        record Mismatch() implements Reservation {}
    }
}
