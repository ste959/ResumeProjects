package com.bonddesk.oms;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;

/**
 * Base class for integration tests that run against a <b>real PostgreSQL</b> rather than
 * H2 — so the tests exercise the actual Flyway migrations and Hibernate schema
 * <em>validation</em>, closing the fidelity gap between dev/test and production.
 *
 * <p>By default a single PostgreSQL container is started via Testcontainers (shared
 * across all test classes, reaped on JVM exit). Alternatively, pass
 * {@code -Dtest.postgres.url=...} to run against an already-running PostgreSQL — handy in
 * CI (a service container) or when the local Docker/Testcontainers combo is unavailable.
 * Requires a Docker daemon only in the Testcontainers path.
 */
@SpringBootTest
@ActiveProfiles("test")
public abstract class AbstractPostgresIntegrationTest {

    private static final String EXTERNAL_URL = System.getProperty("test.postgres.url");

    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("bonddesk")
                    .withUsername("bonddesk")
                    .withPassword("bonddesk");

    static {
        if (EXTERNAL_URL == null) {
            POSTGRES.start();
        }
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        if (EXTERNAL_URL != null) {
            registry.add("spring.datasource.url", () -> EXTERNAL_URL);
            registry.add("spring.datasource.username", () -> System.getProperty("test.postgres.user", "bonddesk"));
            registry.add("spring.datasource.password", () -> System.getProperty("test.postgres.password", "bonddesk"));
        } else {
            registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
            registry.add("spring.datasource.username", POSTGRES::getUsername);
            registry.add("spring.datasource.password", POSTGRES::getPassword);
        }
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
        // Own the schema with Flyway and validate the JPA mappings against it — the prod path.
        registry.add("spring.flyway.enabled", () -> "true");
        registry.add("spring.jpa.hibernate.ddl-auto", () -> "validate");
    }
}
