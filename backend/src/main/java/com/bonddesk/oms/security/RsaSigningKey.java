package com.bonddesk.oms.security;

import java.security.KeyPair;
import java.time.Instant;

/**
 * One RSA signing key in the rotation set: a key pair plus a stable {@code kid} (the RFC 7638 JWK
 * thumbprint of the public key) that tags every token this key signs and lets a verifier look the public
 * key up in the JWKS. The private half signs; only the public half is ever published.
 */
public record RsaSigningKey(String kid, KeyPair keyPair, Instant createdAt) {
}
