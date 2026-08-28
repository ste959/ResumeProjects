package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.Role;
import com.bonddesk.oms.domain.User;
import com.bonddesk.oms.dto.LoginResponse;
import com.bonddesk.oms.dto.TokenResponse;
import com.bonddesk.oms.repository.UserRepository;
import com.bonddesk.oms.security.InMemoryTokenStore;
import com.bonddesk.oms.security.JwtService;
import com.bonddesk.oms.security.KeyManager;
import com.bonddesk.oms.security.TokenStore;
import io.jsonwebtoken.Claims;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/** The login → refresh → logout flows with real JWT + token-store collaborators (only the user repo mocked). */
class AuthServiceTest {

    private final UserRepository users = mock(UserRepository.class);
    private final PasswordEncoder encoder = new BCryptPasswordEncoder();
    private final JwtService jwt = new JwtService(new KeyManager(2), "bonddesk-oms", "bonddesk-api", 15);
    private final TokenStore tokens = new InMemoryTokenStore();
    private final AuthService auth = new AuthService(users, encoder, jwt, tokens, 7);

    @BeforeEach
    void seedTrader() {
        User user = mock(User.class);
        when(user.isEnabled()).thenReturn(true);
        when(user.getUsername()).thenReturn("trader1");
        when(user.getPasswordHash()).thenReturn(encoder.encode("secret"));
        when(user.getRoles()).thenReturn(Set.of(Role.TRADER));
        when(users.findByUsername("trader1")).thenReturn(Optional.of(user));
    }

    @Test
    void loginIssuesAVerifiableAccessTokenPlusARefreshToken() {
        LoginResponse res = auth.login("trader1", "secret");
        assertThat(res.accessToken()).isNotBlank();
        assertThat(res.refreshToken()).isNotBlank();
        assertThat(res.roles()).containsExactly("TRADER");
        assertThat(res.expiresInSeconds()).isEqualTo(15 * 60);
        assertThat(jwt.parse(res.accessToken()).getSubject()).isEqualTo("trader1");
    }

    @Test
    void aWrongPasswordIsRejected() {
        assertThatThrownBy(() -> auth.login("trader1", "wrong")).isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void anUnknownUserIsRejected() {
        // Exercises the branch that runs a dummy BCrypt compare (timing-equalized) then fails.
        assertThatThrownBy(() -> auth.login("ghost", "whatever")).isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void refreshRotatesTheTokenAndTheOldOneStopsWorking() {
        LoginResponse login = auth.login("trader1", "secret");
        TokenResponse refreshed = auth.refresh(login.refreshToken());

        assertThat(refreshed.accessToken()).isNotBlank();
        assertThat(refreshed.refreshToken()).isNotEqualTo(login.refreshToken());
        assertThat(jwt.parse(refreshed.accessToken()).getSubject()).isEqualTo("trader1");
        // The consumed refresh token is dead.
        assertThatThrownBy(() -> auth.refresh(login.refreshToken())).isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void reusingARotatedRefreshTokenBurnsTheWholeFamily() {
        LoginResponse login = auth.login("trader1", "secret");
        TokenResponse rotated = auth.refresh(login.refreshToken());

        // Replay the stolen, already-used token → rejected, and the current token is now dead too.
        assertThatThrownBy(() -> auth.refresh(login.refreshToken())).isInstanceOf(BadCredentialsException.class);
        assertThatThrownBy(() -> auth.refresh(rotated.refreshToken())).isInstanceOf(BadCredentialsException.class);
    }

    @Test
    void logoutRevokesTheAccessTokenAndTheRefreshFamily() {
        LoginResponse login = auth.login("trader1", "secret");
        Claims claims = jwt.parse(login.accessToken());

        auth.logout(login.refreshToken(), "Bearer " + login.accessToken());

        assertThat(tokens.isAccessRevoked(claims.getId())).isTrue();
        assertThatThrownBy(() -> auth.refresh(login.refreshToken())).isInstanceOf(BadCredentialsException.class);
    }
}
