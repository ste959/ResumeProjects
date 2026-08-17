package com.bonddesk.oms.security;

import com.bonddesk.oms.domain.Role;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import org.junit.jupiter.api.Test;

import java.util.EnumSet;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** The JWT round-trip and its rejection of tampered / wrong-key / expired tokens. */
class JwtServiceTest {

    private final JwtService jwt = new JwtService("test-signing-secret-abcdefghij", 60);

    @Test
    void issuesAndParsesSubjectAndRoles() {
        String token = jwt.issue("trader1", EnumSet.of(Role.TRADER, Role.VIEWER));
        Claims claims = jwt.parse(token);
        assertThat(claims.getSubject()).isEqualTo("trader1");
        assertThat(claims.get("roles", List.class)).containsExactlyInAnyOrder("TRADER", "VIEWER");
    }

    @Test
    void rejectsATokenSignedWithADifferentSecret() {
        String forged = new JwtService("a-completely-different-secret", 60).issue("x", EnumSet.of(Role.ADMIN));
        assertThatThrownBy(() -> jwt.parse(forged)).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsGarbage() {
        assertThatThrownBy(() -> jwt.parse("not.a.jwt")).isInstanceOf(Exception.class);
    }

    @Test
    void rejectsAnExpiredToken() {
        JwtService expired = new JwtService("test-signing-secret-abcdefghij", -1);  // issued already expired
        String token = expired.issue("x", EnumSet.of(Role.VIEWER));
        assertThatThrownBy(() -> jwt.parse(token)).isInstanceOf(JwtException.class);
    }
}
