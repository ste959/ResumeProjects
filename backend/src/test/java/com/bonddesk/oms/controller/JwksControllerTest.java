package com.bonddesk.oms.controller;

import com.bonddesk.oms.security.KeyManager;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/** The JWKS exposes exactly the public key material verifiers need — and never anything private. */
class JwksControllerTest {

    private final KeyManager keys = new KeyManager(2);
    private final JwksController controller = new JwksController(keys);

    @Test
    @SuppressWarnings("unchecked")
    void publishesRsaPublicKeysKeyedByKid() {
        keys.rotate();   // now two active keys
        Map<String, Object> jwks = controller.jwks();
        List<Map<String, Object>> keySet = (List<Map<String, Object>>) jwks.get("keys");

        assertThat(keySet).hasSize(2);
        assertThat(keySet).extracting(k -> k.get("kid"))
                .containsExactlyInAnyOrderElementsOf(keys.activeKeys().stream().map(k -> (Object) k.kid()).toList());
        for (Map<String, Object> jwk : keySet) {
            assertThat(jwk.get("kty")).isEqualTo("RSA");
            assertThat(jwk.get("use")).isEqualTo("sig");
            assertThat(jwk.get("alg")).isEqualTo("RS256");
            assertThat(jwk).containsKeys("n", "e");            // the public modulus + exponent
            assertThat(jwk).doesNotContainKeys("d", "p", "q"); // never the private key parameters
        }
    }
}
