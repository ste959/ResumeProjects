package com.bonddesk.oms.security;

import io.jsonwebtoken.security.Jwks;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Holds the RSA signing keys and rotates them. Tokens are signed with the <em>current</em> (newest) key;
 * verification finds the right public key by the token's {@code kid}. On rotation a fresh key becomes
 * current, and the previous key is retained (still in the JWKS, still able to verify) until it ages out —
 * so tokens issued just before a rotation keep validating. This is the standard identity-provider pattern:
 * publish the public keys, rotate the private one, and never break in-flight tokens.
 *
 * <p>Keys are generated in-process at startup (and on {@link #rotate()}). A production deployment would
 * source them from a managed key store (e.g. Azure Key Vault / an HSM) so they survive restarts and are
 * never in application memory longer than needed; that is a drop-in replacement for {@link #generate()}.
 */
@Component
public class KeyManager {

    private static final int KEY_SIZE = 2048;

    /** How many keys to keep verifiable / published in the JWKS (current + previous). */
    private final int retain;

    /** Newest-first, immutable snapshot; swapped atomically on rotation. */
    private final AtomicReference<List<RsaSigningKey>> keys = new AtomicReference<>();

    public KeyManager(@Value("${oms.security.jwt.jwks-retain:2}") int retain) {
        this.retain = Math.max(1, retain);
        this.keys.set(List.of(generate()));
    }

    /** The key new tokens are signed with. */
    public RsaSigningKey current() {
        return keys.get().get(0);
    }

    /** The public key for a token's {@code kid}, or empty if it isn't (or is no longer) a known key. */
    public Optional<PublicKey> verificationKey(String kid) {
        if (kid == null) {
            return Optional.empty();
        }
        return keys.get().stream()
                .filter(k -> k.kid().equals(kid))
                .map(k -> k.keyPair().getPublic())
                .findFirst();
    }

    /** The keys currently published in the JWKS (newest first). */
    public List<RsaSigningKey> activeKeys() {
        return keys.get();
    }

    /**
     * Promote a freshly generated key to current, keeping up to {@code retain} keys so recently-issued
     * tokens signed by the previous key still verify. Triggered operationally (an ADMIN endpoint) or on a
     * schedule wired by the deployment.
     */
    public synchronized RsaSigningKey rotate() {
        RsaSigningKey fresh = generate();
        List<RsaSigningKey> updated = new ArrayList<>();
        updated.add(fresh);
        updated.addAll(keys.get());
        if (updated.size() > retain) {
            updated = new ArrayList<>(updated.subList(0, retain));
        }
        keys.set(List.copyOf(updated));
        return fresh;
    }

    private static RsaSigningKey generate() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(KEY_SIZE);
            KeyPair pair = generator.generateKeyPair();
            // kid = the RFC 7638 JWK thumbprint of the public key — stable and derivable by any verifier.
            String kid = Jwks.builder().key((RSAPublicKey) pair.getPublic()).idFromThumbprint().build().getId();
            return new RsaSigningKey(kid, pair, Instant.now());
        } catch (Exception e) {
            throw new IllegalStateException("RSA key generation failed", e);
        }
    }
}
