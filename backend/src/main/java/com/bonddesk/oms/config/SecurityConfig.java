package com.bonddesk.oms.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Authentication/authorization for the OMS API. The mutating surface (order create/route/fill/cancel,
 * rebalance, paper orders) must not be open to anyone who can reach the port.
 *
 * <p>Enforcement is config-gated so the OMS still boots and every test/dev flow runs unauthenticated
 * by default:
 * <ul>
 *   <li>{@code oms.security.enabled=false} (default): the chain permits all requests — the security
 *       infrastructure is wired but not enforcing, keeping the laptop/demo experience frictionless.</li>
 *   <li>{@code oms.security.enabled=true} (set it in any real deployment): reads, health/info,
 *       swagger and the market-data WebSockets stay open, but every state-changing request must carry
 *       a valid {@code X-API-Key}. Set {@code oms.security.api-key} to a strong secret from the
 *       environment.</li>
 * </ul>
 * The request is stateless (no session) and CSRF is disabled because auth is a per-request API key,
 * not a cookie.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http,
                                           @Value("${oms.security.enabled:false}") boolean enabled,
                                           @Value("${oms.security.api-key:}") String apiKey) throws Exception {
        http.csrf(csrf -> csrf.disable())
            .cors(Customizer.withDefaults())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .headers(h -> h.frameOptions(fo -> fo.sameOrigin())); // H2 console frame when locally enabled

        if (!enabled) {
            http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
            return http.build();
        }

        http.addFilterBefore(new ApiKeyAuthFilter(apiKey), UsernamePasswordAuthenticationFilter.class)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health/**", "/actuator/info").permitAll()
                .requestMatchers("/swagger-ui/**", "/v3/api-docs/**").permitAll()
                .requestMatchers("/ws/**").permitAll()                    // read-only market-data push
                .requestMatchers(HttpMethod.GET, "/**").permitAll()       // reads are open
                .anyRequest().authenticated());                           // writes require the API key
        return http.build();
    }
}
