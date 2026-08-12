package com.bonddesk.oms.config;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

/** The API-key authentication logic: a valid key authenticates; anything else stays anonymous. */
class ApiKeyAuthFilterTest {

    @AfterEach
    void clear() {
        SecurityContextHolder.clearContext();
    }

    private void run(String expectedKey, String providedHeader) throws Exception {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/orders");
        if (providedHeader != null) {
            req.addHeader("X-API-Key", providedHeader);
        }
        new ApiKeyAuthFilter(expectedKey).doFilter(req, new MockHttpServletResponse(), new MockFilterChain());
    }

    @Test
    void authenticatesOnMatchingKey() throws Exception {
        run("s3cret", "s3cret");
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNotNull();
        assertThat(SecurityContextHolder.getContext().getAuthentication().isAuthenticated()).isTrue();
    }

    @Test
    void rejectsWrongKey() throws Exception {
        run("s3cret", "guess");
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    }

    @Test
    void rejectsMissingHeader() throws Exception {
        run("s3cret", null);
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    }

    @Test
    void blankExpectedKeyNeverAuthenticates() throws Exception {
        // Guards against a misconfiguration where an empty api-key would accept an empty header.
        run("", "");
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    }
}
