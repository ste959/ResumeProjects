package com.bonddesk.oms.config;

import com.bonddesk.oms.compliance.ComplianceProperties;
import com.bonddesk.oms.equities.AlpacaProperties;
import com.bonddesk.oms.fixedincome.FixedIncomeProperties;
import com.bonddesk.oms.market.CoinbaseProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Clock;

/**
 * Core beans. Exposing {@link Clock} as a bean (rather than calling
 * {@code Instant.now()} directly) lets tests inject a fixed clock and assert on
 * timestamps deterministically.
 */
@Configuration
@EnableConfigurationProperties({ComplianceProperties.class, CoinbaseProperties.class,
        AlpacaProperties.class, FixedIncomeProperties.class})
public class AppConfig {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
