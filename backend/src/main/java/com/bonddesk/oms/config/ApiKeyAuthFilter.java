package com.bonddesk.oms.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Authenticates a request when it carries a valid {@code X-API-Key} header. A match populates the
 * {@link SecurityContextHolder} with an authenticated principal so downstream authorization lets the
 * request through; no header (or a wrong one) leaves the context anonymous, and protected endpoints
 * respond 401/403. Always in the chain (see {@code SecurityConfig}); inert unless an
 * {@code oms.security.api-key} is configured.
 */
public class ApiKeyAuthFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-API-Key";
    private final String expectedKey;

    public ApiKeyAuthFilter(String expectedKey) {
        this.expectedKey = expectedKey;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String provided = request.getHeader(HEADER);
        // Constant-time compare avoids leaking key length/prefix through timing.
        if (expectedKey != null && !expectedKey.isBlank() && provided != null
                && java.security.MessageDigest.isEqual(
                        expectedKey.getBytes(java.nio.charset.StandardCharsets.UTF_8),
                        provided.getBytes(java.nio.charset.StandardCharsets.UTF_8))) {
            var authentication = new UsernamePasswordAuthenticationToken(
                    "api-client", null, AuthorityUtils.createAuthorityList("ROLE_SERVICE"));
            SecurityContextHolder.getContext().setAuthentication(authentication);
        }
        chain.doFilter(request, response);
    }
}
