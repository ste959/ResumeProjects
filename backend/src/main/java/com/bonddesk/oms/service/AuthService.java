package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.User;
import com.bonddesk.oms.dto.LoginResponse;
import com.bonddesk.oms.repository.UserRepository;
import com.bonddesk.oms.security.JwtService;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/** Validates credentials and issues a signed JWT. Failure modes are indistinguishable (unknown user vs
 *  wrong password vs disabled account all yield the same error) so the endpoint can't be used to
 *  enumerate valid usernames. */
@Service
public class AuthService {

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final JwtService jwt;

    public AuthService(UserRepository users, PasswordEncoder encoder, JwtService jwt) {
        this.users = users;
        this.encoder = encoder;
        this.jwt = jwt;
    }

    public LoginResponse login(String username, String password) {
        User user = users.findByUsername(username)
                .filter(User::isEnabled)
                .orElseThrow(() -> new BadCredentialsException("invalid username or password"));
        if (!encoder.matches(password, user.getPasswordHash())) {
            throw new BadCredentialsException("invalid username or password");
        }
        String token = jwt.issue(user.getUsername(), user.getRoles());
        return new LoginResponse(token, "Bearer", user.getUsername(),
                user.getRoles().stream().map(Enum::name).sorted().toList(), jwt.ttlMinutes());
    }
}
