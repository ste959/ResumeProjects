package com.bonddesk.oms.controller;

import com.bonddesk.oms.dto.LoginRequest;
import com.bonddesk.oms.dto.LoginResponse;
import com.bonddesk.oms.dto.RefreshRequest;
import com.bonddesk.oms.dto.TokenResponse;
import com.bonddesk.oms.dto.UserInfo;
import com.bonddesk.oms.security.KeyManager;
import com.bonddesk.oms.security.RsaSigningKey;
import com.bonddesk.oms.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/auth")
@Tag(name = "Identity", description = "Login, token refresh, logout, and key rotation")
public class AuthController {

    private final AuthService auth;
    private final KeyManager keys;

    public AuthController(AuthService auth, KeyManager keys) {
        this.auth = auth;
        this.keys = keys;
    }

    @PostMapping("/login")
    @Operation(summary = "Exchange username/password for a short-lived access token + a refresh token")
    public LoginResponse login(@Valid @RequestBody LoginRequest request) {
        return auth.login(request.username(), request.password());
    }

    @PostMapping("/refresh")
    @Operation(summary = "Rotate a refresh token for a new access token (replay of a used token is rejected)")
    public TokenResponse refresh(@Valid @RequestBody RefreshRequest request) {
        return auth.refresh(request.refreshToken());
    }

    @PostMapping("/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Operation(summary = "Revoke the refresh-token family and denylist the current access token")
    public void logout(@RequestBody(required = false) RefreshRequest request,
                       @RequestHeader(value = "Authorization", required = false) String authorization) {
        auth.logout(request == null ? null : request.refreshToken(), authorization);
    }

    @GetMapping("/me")
    @Operation(summary = "The authenticated user and their roles (from the bearer token)")
    public UserInfo me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities().stream()
                .map(a -> a.getAuthority().replaceFirst("^ROLE_", ""))
                .sorted().toList();
        return new UserInfo(authentication.getName(), roles);
    }

    @PreAuthorize("hasRole('ADMIN')")
    @PostMapping("/keys/rotate")
    @Operation(summary = "Rotate the signing key (ADMIN). The previous key stays in the JWKS until its tokens expire.")
    public Map<String, Object> rotateKey() {
        RsaSigningKey fresh = keys.rotate();
        return Map.of("currentKid", fresh.kid(),
                "activeKids", keys.activeKeys().stream().map(RsaSigningKey::kid).toList());
    }
}
