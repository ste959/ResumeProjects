package com.bonddesk.oms.controller;

import com.bonddesk.oms.security.KeyManager;
import io.jsonwebtoken.security.Jwk;
import io.jsonwebtoken.security.Jwks;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.security.interfaces.RSAPublicKey;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Publishes the JSON Web Key Set — the <b>public</b> halves of the active signing keys, keyed by
 * {@code kid}. Any service can fetch this to verify a token without a shared secret and, because retired
 * keys stay listed until their tokens expire, verification keeps working across a key rotation. Only
 * public key material (modulus + exponent) is ever exposed here; the private keys never leave the process.
 */
@RestController
@Tag(name = "Identity", description = "Token signing keys (JWKS)")
public class JwksController {

    private final KeyManager keys;

    public JwksController(KeyManager keys) {
        this.keys = keys;
    }

    @GetMapping({"/.well-known/jwks.json", "/oauth2/jwks"})
    @Operation(summary = "JSON Web Key Set — public keys for verifying access tokens")
    public Map<String, Object> jwks() {
        List<Map<String, Object>> jwkList = keys.activeKeys().stream()
                .map(k -> {
                    Jwk<?> jwk = Jwks.builder()
                            .key((RSAPublicKey) k.keyPair().getPublic())
                            .id(k.kid())
                            .build();
                    Map<String, Object> entry = new LinkedHashMap<>(jwk);   // Jwk is a Map of the public params
                    entry.put("use", "sig");
                    entry.put("alg", "RS256");
                    return entry;
                })
                .toList();
        return Map.of("keys", jwkList);
    }
}
