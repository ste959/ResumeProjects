package com.bonddesk.oms.controller;

import com.bonddesk.oms.dto.LoginRequest;
import com.bonddesk.oms.dto.LoginResponse;
import com.bonddesk.oms.dto.UserInfo;
import com.bonddesk.oms.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final AuthService auth;

    public AuthController(AuthService auth) {
        this.auth = auth;
    }

    @PostMapping("/login")
    @Operation(summary = "Exchange username/password for a signed JWT bearer token")
    public LoginResponse login(@Valid @RequestBody LoginRequest request) {
        return auth.login(request.username(), request.password());
    }

    @GetMapping("/me")
    @Operation(summary = "The authenticated user and their roles (from the bearer token)")
    public UserInfo me(Authentication authentication) {
        var roles = authentication.getAuthorities().stream()
                .map(a -> a.getAuthority().replaceFirst("^ROLE_", ""))
                .sorted().toList();
        return new UserInfo(authentication.getName(), roles);
    }
}
