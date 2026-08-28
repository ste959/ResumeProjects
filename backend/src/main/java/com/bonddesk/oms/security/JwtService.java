package com.bonddesk.oms.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.LocatorAdapter;
import io.jsonwebtoken.ProtectedHeader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.security.Key;
import java.time.Duration;
import java.time.Instant;
import java.util.Collection;
import java.util.Date;
import java.util.List;
import java.util.UUID;

/**
 * Issues and verifies the short-lived <b>access token</b> as an asymmetrically-signed (RS256) JWT.
 *
 * <p>Tokens are signed with the {@link KeyManager}'s current private key and tagged with its {@code kid};
 * a verifier resolves the matching public key by {@code kid} (published at the JWKS endpoint), so no
 * shared secret is ever needed to validate a token — the identity pattern real IdPs use. Every token
 * carries the standard registered claims a resource server checks: issuer, audience, a unique {@code jti}
 * (so an individual token can be revoked), {@code iat}/{@code nbf}/{@code exp}, plus the user's roles.
 */
@Service
public class JwtService {

    private final KeyManager keys;
    private final String issuer;
    private final String audience;
    private final Duration accessTtl;

    public JwtService(KeyManager keys,
                      @Value("${oms.security.jwt.issuer:bonddesk-oms}") String issuer,
                      @Value("${oms.security.jwt.audience:bonddesk-api}") String audience,
                      @Value("${oms.security.jwt.access-ttl-minutes:15}") long accessTtlMinutes) {
        this.keys = keys;
        this.issuer = issuer;
        this.audience = audience;
        this.accessTtl = Duration.ofMinutes(accessTtlMinutes);
    }

    /** Sign a short-lived access token for a user. */
    public String issueAccessToken(String username, Collection<String> roles) {
        RsaSigningKey signing = keys.current();
        Instant now = Instant.now();
        return Jwts.builder()
                .header().keyId(signing.kid()).and()
                .issuer(issuer)
                .audience().add(audience).and()
                .subject(username)
                .id(UUID.randomUUID().toString())                 // jti — the handle for revocation
                .claim("roles", List.copyOf(roles))
                .issuedAt(Date.from(now))
                .notBefore(Date.from(now))
                .expiration(Date.from(now.plus(accessTtl)))
                .signWith(signing.keyPair().getPrivate(), Jwts.SIG.RS256)
                .compact();
    }

    /**
     * Verify a token and return its claims. The public key is chosen by the token's {@code kid} (so key
     * rotation is transparent), the signature and {@code exp}/{@code nbf} are checked by the parser, and
     * the issuer and audience are asserted. Throws {@link JwtException} for anything invalid, tampered,
     * wrong-key, expired, or aimed at a different audience.
     */
    public Claims parse(String token) {
        Claims claims = Jwts.parser()
                .keyLocator(new LocatorAdapter<Key>() {
                    @Override
                    protected Key locate(ProtectedHeader header) {
                        return keys.verificationKey(header.getKeyId()).orElse(null);
                    }
                })
                .requireIssuer(issuer)
                .build()
                .parseSignedClaims(token)
                .getPayload();
        // jjwt exposes aud as a set; assert this token was minted for us.
        if (claims.getAudience() == null || !claims.getAudience().contains(audience)) {
            throw new JwtException("token audience is not " + audience);
        }
        return claims;
    }

    public long accessTtlSeconds() {
        return accessTtl.toSeconds();
    }
}
