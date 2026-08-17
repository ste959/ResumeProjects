package com.bonddesk.oms.security;

import com.bonddesk.oms.domain.Role;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.Set;

/**
 * Issues and verifies signed JWTs for user authentication. Tokens carry the username (subject) and the
 * user's roles; they are HMAC-signed with a secret from the environment (never committed). The secret is
 * SHA-256-derived to a 256-bit key so any configured string is a valid HS256 key.
 */
@Service
public class JwtService {

    private final SecretKey key;
    private final Duration ttl;

    public JwtService(@Value("${oms.security.jwt.secret:}") String secret,
                      @Value("${oms.security.jwt.ttl-minutes:60}") long ttlMinutes) {
        this.key = deriveKey(secret);
        this.ttl = Duration.ofMinutes(ttlMinutes);
    }

    /** Sign a token for a user. */
    public String issue(String username, Set<Role> roles) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(username)
                .claim("roles", roles.stream().map(Enum::name).toList())
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(ttl)))
                .signWith(key)
                .compact();
    }

    /** Verify a token and return its claims. Throws {@code io.jsonwebtoken.JwtException} if invalid,
     *  tampered, wrong-key, or expired. */
    public Claims parse(String token) {
        return Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
    }

    public long ttlMinutes() {
        return ttl.toMinutes();
    }

    private static SecretKey deriveKey(String secret) {
        // A dev-only default keeps local/test flows working; set OMS_JWT_SECRET in any real deployment.
        byte[] raw = (secret == null || secret.isBlank())
                ? "dev-only-insecure-jwt-signing-key-change-me".getBytes(StandardCharsets.UTF_8)
                : secret.getBytes(StandardCharsets.UTF_8);
        try {
            return Keys.hmacShaKeyFor(MessageDigest.getInstance("SHA-256").digest(raw));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
