package com.bonddesk.oms.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import org.junit.jupiter.api.Test;

import java.util.Base64;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** RS256 access tokens: the claims round-trip, key rotation is transparent, and the parser rejects a
 *  wrong audience/issuer, an unknown signing key, and an expired token. */
class JwtServiceTest {

    private final KeyManager keys = new KeyManager(2);
    private final JwtService jwt = new JwtService(keys, "bonddesk-oms", "bonddesk-api", 15);

    @Test
    void issuesAndParsesTheStandardClaims() {
        String token = jwt.issueAccessToken("trader1", List.of("TRADER", "VIEWER"));
        Claims claims = jwt.parse(token);
        assertThat(claims.getSubject()).isEqualTo("trader1");
        assertThat(claims.get("roles", List.class)).containsExactlyInAnyOrder("TRADER", "VIEWER");
        assertThat(claims.getIssuer()).isEqualTo("bonddesk-oms");
        assertThat(claims.getAudience()).contains("bonddesk-api");
        assertThat(claims.getId()).isNotBlank();   // jti — the revocation handle
    }

    @Test
    void theHeaderIsSignedRs256AndTaggedWithTheCurrentKid() {
        String token = jwt.issueAccessToken("u", List.of("VIEWER"));
        String header = new String(Base64.getUrlDecoder().decode(token.split("\\.")[0]));
        assertThat(header).contains("\"alg\":\"RS256\"");
        assertThat(header).contains(keys.current().kid());
    }

    @Test
    void rejectsAWrongAudience() {
        String token = jwt.issueAccessToken("u", List.of("VIEWER"));
        JwtService wrongAudience = new JwtService(keys, "bonddesk-oms", "some-other-api", 15);
        assertThatThrownBy(() -> wrongAudience.parse(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsAWrongIssuer() {
        String token = jwt.issueAccessToken("u", List.of("VIEWER"));
        JwtService wrongIssuer = new JwtService(keys, "some-other-issuer", "bonddesk-api", 15);
        assertThatThrownBy(() -> wrongIssuer.parse(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsATokenSignedByAKeyItDoesNotKnow() {
        // A different KeyManager = a different (unknown) kid → our parser can't resolve a verification key.
        JwtService forger = new JwtService(new KeyManager(2), "bonddesk-oms", "bonddesk-api", 15);
        String forged = forger.issueAccessToken("x", List.of("ADMIN"));
        assertThatThrownBy(() -> jwt.parse(forged)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsAnExpiredToken() {
        JwtService expired = new JwtService(keys, "bonddesk-oms", "bonddesk-api", -1);   // exp in the past
        String token = expired.issueAccessToken("x", List.of("VIEWER"));
        assertThatThrownBy(() -> jwt.parse(token)).isInstanceOf(JwtException.class);
    }

    @Test
    void aTokenStillVerifiesAfterAKeyRotation() {
        String beforeRotation = jwt.issueAccessToken("u", List.of("VIEWER"));
        String oldKid = keys.current().kid();

        keys.rotate();
        assertThat(keys.current().kid()).isNotEqualTo(oldKid);
        String afterRotation = jwt.issueAccessToken("u", List.of("VIEWER"));

        // retain=2, so the previous key is still published → the pre-rotation token still validates.
        assertThat(jwt.parse(beforeRotation).getSubject()).isEqualTo("u");
        assertThat(jwt.parse(afterRotation).getSubject()).isEqualTo("u");
    }

    @Test
    void aTokenStopsVerifyingOnceItsKeyAgesOutOfTheRetainWindow() {
        String token = jwt.issueAccessToken("u", List.of("VIEWER"));
        keys.rotate();   // retain=2: key still present
        keys.rotate();   // now the original key is evicted
        assertThatThrownBy(() -> jwt.parse(token)).isInstanceOf(JwtException.class);
    }
}
