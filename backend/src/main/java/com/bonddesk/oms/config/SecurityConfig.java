package com.bonddesk.oms.config;

import com.bonddesk.oms.security.JwtAuthenticationFilter;
import com.bonddesk.oms.security.JwtService;
import com.bonddesk.oms.security.TokenStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Authentication and authorization for the OMS API.
 *
 * <p>Two authentication mechanisms, both stateless (no session, no CSRF token — auth is per-request):
 * <ul>
 *   <li><b>JWT</b> for human users — a login-issued {@code Authorization: Bearer} token whose roles
 *       ({@code VIEWER}/{@code TRADER}/{@code ADMIN}) become authorities (see {@link JwtService},
 *       {@link JwtAuthenticationFilter}).</li>
 *   <li><b>API key</b> for machine/automation — a valid {@code X-API-Key} grants {@code ROLE_SERVICE}
 *       (see {@link ApiKeyAuthFilter}); inert when no key is configured.</li>
 * </ul>
 *
 * <p>Authorization: reads (market data) are public; <b>state-changing endpoints require a role</b>,
 * enforced with method security ({@code @PreAuthorize}) on the controllers. Enforcement is always on.
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http, JwtService jwt, TokenStore tokens,
                                           @Value("${oms.security.api-key:}") String apiKey) throws Exception {
        http.csrf(csrf -> csrf.disable())
            .cors(Customizer.withDefaults())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .headers(h -> h.frameOptions(fo -> fo.sameOrigin()))
            .addFilterBefore(new JwtAuthenticationFilter(jwt, tokens), UsernamePasswordAuthenticationFilter.class)
            .addFilterBefore(new ApiKeyAuthFilter(apiKey), UsernamePasswordAuthenticationFilter.class)
            .authorizeHttpRequests(auth -> auth
                // Token endpoints reachable without an access token (they mint/rotate/revoke tokens).
                .requestMatchers("/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout").permitAll()
                .requestMatchers("/.well-known/jwks.json", "/oauth2/jwks").permitAll()   // public verification keys
                .requestMatchers("/actuator/health/**", "/actuator/info").permitAll()
                .requestMatchers("/swagger-ui/**", "/v3/api-docs/**").permitAll()
                .requestMatchers("/ws/**").permitAll()                    // read-only market-data push
                // The standalone matching-engine terminal and crypto-market are login-less public
                // sandboxes (interactive "play with the engine" demos, no real desk state), so their
                // writes are public too. The regulated OMS desk below still requires a role.
                .requestMatchers("/api/exchange/**", "/api/market/**").permitAll()
                .requestMatchers("/api/v1/auth/me").authenticated()       // who am I → must be logged in
                // All GET reads are public in this DEMO — quotes/order books AND the blotter, positions,
                // and paper-account views. That's a deliberate read-only public surface (no real customer
                // data); lock the account/blotter reads behind authenticated()/roles for a real deployment.
                .requestMatchers(HttpMethod.GET, "/**").permitAll()
                .anyRequest().authenticated())                            // writes require a valid principal
            .exceptionHandling(e -> e.authenticationEntryPoint(
                (request, response, ex) -> response.sendError(401, "authentication required")));
        return http.build();
    }
}
