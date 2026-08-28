package com.bonddesk.oms.dto;

import java.util.List;

/**
 * Result of a successful login: a short-lived {@code accessToken} to send as a bearer, and a long-lived
 * {@code refreshToken} to exchange for new access tokens without re-entering credentials.
 */
public record LoginResponse(String accessToken, String refreshToken, String tokenType, String username,
                            List<String> roles, long expiresInSeconds) {
}
