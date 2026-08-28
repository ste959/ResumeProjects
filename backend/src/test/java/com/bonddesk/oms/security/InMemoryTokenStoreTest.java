package com.bonddesk.oms.security;

import com.bonddesk.oms.security.TokenStore.RefreshOutcome;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import static org.assertj.core.api.Assertions.assertThat;

/** The refresh-token lifecycle (rotation + reuse detection + family revocation) and the access denylist. */
class InMemoryTokenStoreTest {

    private final AtomicLong clock = new AtomicLong(1_000);
    private final InMemoryTokenStore store = new InMemoryTokenStore(clock::get);
    private final Duration ttl = Duration.ofDays(7);

    @Test
    void rotatingARefreshTokenIssuesANewOneForTheSameIdentity() {
        String rt = store.issueRefresh("trader1", List.of("TRADER"), ttl);
        RefreshOutcome outcome = store.rotateRefresh(rt, ttl);

        assertThat(outcome).isInstanceOf(RefreshOutcome.Rotated.class);
        RefreshOutcome.Rotated rotated = (RefreshOutcome.Rotated) outcome;
        assertThat(rotated.username()).isEqualTo("trader1");
        assertThat(rotated.roles()).containsExactly("TRADER");
        assertThat(rotated.newRefreshToken()).isNotEqualTo(rt);
    }

    @Test
    void theOldTokenIsDeadAfterRotation() {
        String rt = store.issueRefresh("u", List.of("VIEWER"), ttl);
        store.rotateRefresh(rt, ttl);
        // Presenting the already-rotated token again is a replay.
        assertThat(store.rotateRefresh(rt, ttl)).isInstanceOf(RefreshOutcome.Reused.class);
    }

    @Test
    void reuseOfARotatedTokenRevokesTheWholeFamily() {
        String rt1 = store.issueRefresh("u", List.of("VIEWER"), ttl);
        String rt2 = ((RefreshOutcome.Rotated) store.rotateRefresh(rt1, ttl)).newRefreshToken();

        // The attacker replays the stolen, already-used rt1 → reuse detected.
        assertThat(store.rotateRefresh(rt1, ttl)).isInstanceOf(RefreshOutcome.Reused.class);
        // ...and the legitimate current token rt2 is now dead too (whole family burned).
        assertThat(store.rotateRefresh(rt2, ttl)).isInstanceOf(RefreshOutcome.Invalid.class);
    }

    @Test
    void logoutRevokesTheFamily() {
        String rt = store.issueRefresh("u", List.of("VIEWER"), ttl);
        store.revokeRefreshFamily(rt);
        assertThat(store.rotateRefresh(rt, ttl)).isInstanceOf(RefreshOutcome.Invalid.class);
    }

    @Test
    void anUnknownOrExpiredRefreshTokenIsInvalid() {
        assertThat(store.rotateRefresh("never-issued", ttl)).isInstanceOf(RefreshOutcome.Invalid.class);
        String rt = store.issueRefresh("u", List.of("VIEWER"), Duration.ofMinutes(10));
        clock.addAndGet(Duration.ofMinutes(11).toMillis());
        assertThat(store.rotateRefresh(rt, ttl)).isInstanceOf(RefreshOutcome.Invalid.class);
    }

    @Test
    void accessTokenRevocationExpiresWithTheToken() {
        store.revokeAccess("jti-1", Duration.ofSeconds(30));
        assertThat(store.isAccessRevoked("jti-1")).isTrue();
        clock.addAndGet(Duration.ofSeconds(31).toMillis());
        assertThat(store.isAccessRevoked("jti-1")).isFalse();   // denylist entry ages out with the token
        assertThat(store.isAccessRevoked("never-revoked")).isFalse();
    }
}
