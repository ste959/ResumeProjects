package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.User;
import com.bonddesk.oms.dto.LoginResponse;
import com.bonddesk.oms.dto.TokenResponse;
import com.bonddesk.oms.repository.UserRepository;
import com.bonddesk.oms.security.JwtService;
import com.bonddesk.oms.security.TokenStore;
import com.bonddesk.oms.security.TokenStore.RefreshOutcome;
import io.jsonwebtoken.Claims;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * The identity flows: login, refresh, and logout.
 *
 * <p>Login validates credentials — with indistinguishable failures (unknown user vs wrong password vs
 * disabled all yield the same error, so it can't enumerate usernames) — then issues a short-lived access
 * token plus a rotating refresh token. Refresh rotates the refresh token and detects replay of a stolen
 * one; logout revokes the refresh family and denylists the current access token's {@code jti}.
 */
@Service
public class AuthService {

    private static final Logger log = LoggerFactory.getLogger(AuthService.class);

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final JwtService jwt;
    private final TokenStore tokens;
    private final Duration refreshTtl;
    /** A real BCrypt hash to compare against when the user doesn't exist, so both paths cost the same. */
    private final String dummyHash;

    public AuthService(UserRepository users, PasswordEncoder encoder, JwtService jwt, TokenStore tokens,
                       @Value("${oms.security.jwt.refresh-ttl-days:7}") long refreshTtlDays) {
        this.users = users;
        this.encoder = encoder;
        this.jwt = jwt;
        this.tokens = tokens;
        this.refreshTtl = Duration.ofDays(refreshTtlDays);
        this.dummyHash = encoder.encode("no-such-user-timing-equalizer");
    }

    public LoginResponse login(String username, String password) {
        Optional<User> found = users.findByUsername(username).filter(User::isEnabled);
        // Always run a BCrypt comparison — against the real hash or a dummy of equal cost — so an unknown
        // (or disabled) user takes the same wall-clock time as a wrong password, closing the timing oracle
        // that message-indistinguishability alone would leave open (username enumeration).
        String hash = found.map(User::getPasswordHash).orElse(dummyHash);
        boolean matches = encoder.matches(password, hash);
        if (found.isEmpty() || !matches) {
            throw new BadCredentialsException("invalid username or password");
        }
        User user = found.get();
        List<String> roles = user.getRoles().stream().map(Enum::name).sorted().toList();
        String access = jwt.issueAccessToken(user.getUsername(), roles);
        String refresh = tokens.issueRefresh(user.getUsername(), roles, refreshTtl);
        return new LoginResponse(access, refresh, "Bearer", user.getUsername(), roles, jwt.accessTtlSeconds());
    }

    public TokenResponse refresh(String refreshToken) {
        RefreshOutcome outcome = tokens.rotateRefresh(refreshToken, refreshTtl);
        if (outcome instanceof RefreshOutcome.Rotated rotated) {
            String access = jwt.issueAccessToken(rotated.username(), rotated.roles());
            return new TokenResponse(access, rotated.newRefreshToken(), "Bearer", jwt.accessTtlSeconds());
        }
        if (outcome instanceof RefreshOutcome.Reused) {
            // The family is now revoked; treat as auth failure but log it — this is a theft signal.
            log.warn("Refresh-token reuse detected; the token family has been revoked");
        }
        throw new BadCredentialsException("invalid refresh token");
    }

    /** Best-effort logout: kill the refresh family, and denylist the current access token for its remainder. */
    public void logout(String refreshToken, String authorizationHeader) {
        if (refreshToken != null && !refreshToken.isBlank()) {
            tokens.revokeRefreshFamily(refreshToken);
        }
        if (authorizationHeader != null && authorizationHeader.startsWith("Bearer ")) {
            try {
                Claims claims = jwt.parse(authorizationHeader.substring(7));
                long remaining = claims.getExpiration().toInstant().getEpochSecond() - Instant.now().getEpochSecond();
                if (claims.getId() != null && remaining > 0) {
                    tokens.revokeAccess(claims.getId(), Duration.ofSeconds(remaining));
                }
            } catch (Exception ignored) {
                // No/invalid access token on logout is fine — revoking the refresh family already suffices.
            }
        }
    }
}
