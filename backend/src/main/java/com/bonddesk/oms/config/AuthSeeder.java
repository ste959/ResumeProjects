package com.bonddesk.oms.config;

import com.bonddesk.oms.domain.Role;
import com.bonddesk.oms.domain.User;
import com.bonddesk.oms.repository.UserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.EnumSet;

/**
 * Seeds demo users on first boot so the login flow is usable out of the box. DISABLE in any real
 * deployment ({@code oms.security.seed-demo-users=false}) — these are well-known weak credentials.
 */
@Component
@ConditionalOnProperty(prefix = "oms.security", name = "seed-demo-users", havingValue = "true",
        matchIfMissing = true)
public class AuthSeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AuthSeeder.class);

    private final UserRepository users;
    private final PasswordEncoder encoder;

    public AuthSeeder(UserRepository users, PasswordEncoder encoder) {
        this.users = users;
        this.encoder = encoder;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (users.count() > 0) {
            return;
        }
        users.save(new User("admin", encoder.encode("admin"), EnumSet.of(Role.ADMIN)));
        users.save(new User("trader", encoder.encode("trader"), EnumSet.of(Role.TRADER)));
        users.save(new User("viewer", encoder.encode("viewer"), EnumSet.of(Role.VIEWER)));
        log.warn("Seeded DEMO users (admin/admin, trader/trader, viewer/viewer). These are weak, "
                + "well-known credentials — change them or set oms.security.seed-demo-users=false in prod.");
    }
}
