package com.bonddesk.oms.idempotency;

import com.bonddesk.oms.idempotency.IdempotencyStore.Reservation;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;

/** The reservation state machine: acquire → in-flight → complete → replay, plus mismatch and expiry. */
class InMemoryIdempotencyStoreTest {

    private final AtomicLong clock = new AtomicLong(1_000);
    private final InMemoryIdempotencyStore store =
            new InMemoryIdempotencyStore(60_000, clock::get);   // 60s ttl, controllable clock

    @Test
    void firstUseAcquiresTheKey() {
        assertThat(store.begin("k1", "fp")).isInstanceOf(Reservation.Acquired.class);
    }

    @Test
    void aSecondCallWhileInFlightIsReportedInFlight() {
        store.begin("k1", "fp");                                  // acquired, not yet completed
        assertThat(store.begin("k1", "fp")).isInstanceOf(Reservation.InFlight.class);
    }

    @Test
    void afterCompletionTheSameKeyReplaysTheStoredResult() {
        store.begin("k1", "fp");
        store.complete("k1", "ORDER-42");
        Reservation replay = store.begin("k1", "fp");
        assertThat(replay).isInstanceOf(Reservation.Replay.class);
        assertThat(((Reservation.Replay) replay).result()).isEqualTo("ORDER-42");
    }

    @Test
    void sameKeyWithADifferentBodyIsAMismatch() {
        store.begin("k1", "fingerprint-A");
        store.complete("k1", "ORDER-42");
        assertThat(store.begin("k1", "fingerprint-B")).isInstanceOf(Reservation.Mismatch.class);
    }

    @Test
    void releasingAReservationLetsTheKeyBeAcquiredAgain() {
        store.begin("k1", "fp");
        store.release("k1");
        assertThat(store.begin("k1", "fp")).isInstanceOf(Reservation.Acquired.class);
    }

    @Test
    void releaseNeverDropsACompletedOutcome() {
        store.begin("k1", "fp");
        store.complete("k1", "ORDER-42");
        store.release("k1");   // must be a no-op — a retry can still replay
        assertThat(store.begin("k1", "fp")).isInstanceOf(Reservation.Replay.class);
    }

    @Test
    void anExpiredKeyCanBeAcquiredAfresh() {
        store.begin("k1", "fp");
        store.complete("k1", "ORDER-42");
        clock.addAndGet(60_001);   // step past the ttl
        assertThat(store.begin("k1", "fp")).isInstanceOf(Reservation.Acquired.class);
    }
}
