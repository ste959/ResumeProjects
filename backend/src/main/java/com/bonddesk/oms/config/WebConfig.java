package com.bonddesk.oms.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Allows the React dev server to call the API during local development. The allowed
 * origin is configurable so it can be locked down per environment.
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final String allowedOriginPatterns;

    public WebConfig(@Value("${oms.cors.allowed-origins:http://localhost:*}") String allowedOriginPatterns) {
        this.allowedOriginPatterns = allowedOriginPatterns;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        // Origin *patterns* (not fixed origins) so any localhost port works in dev and
        // when the UI is served through nginx on a different port. Lock this down to the
        // real domain(s) in production via oms.cors.allowed-origins.
        registry.addMapping("/api/**")
                .allowedOriginPatterns(allowedOriginPatterns.split(","))
                .allowedMethods("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS");
    }
}
