package com.bonddesk.oms.config;

import com.bonddesk.oms.security.JwtAuthenticationFilter;
import com.bonddesk.oms.security.JwtService;
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
    public SecurityFilterChain filterChain(HttpSecurity http, JwtService jwt,
                                           @Value("${oms.security.api-key:}") String apiKey) throws Exception {
        http.csrf(csrf -> csrf.disable())
            .cors(Customizer.withDefaults())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .headers(h -> h.frameOptions(fo -> fo.sameOrigin()))
            .addFilterBefore(new JwtAuthenticationFilter(jwt), UsernamePasswordAuthenticationFilter.class)
            .addFilterBefore(new ApiKeyAuthFilter(apiKey), UsernamePasswordAuthenticationFilter.class)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/v1/auth/login").permitAll()
                .requestMatchers("/actuator/health/**", "/actuator/info").permitAll()
                .requestMatchers("/swagger-ui/**", "/v3/api-docs/**").permitAll()
                .requestMatchers("/ws/**").permitAll()                    // read-only market-data push
                .requestMatchers("/api/v1/auth/me").authenticated()       // who am I → must be logged in
                .requestMatchers(HttpMethod.GET, "/**").permitAll()       // reads (market data) are public
                .anyRequest().authenticated())                            // writes require a valid principal
            .exceptionHandling(e -> e.authenticationEntryPoint(
                (request, response, ex) -> response.sendError(401, "authentication required")));
        return http.build();
    }
}
