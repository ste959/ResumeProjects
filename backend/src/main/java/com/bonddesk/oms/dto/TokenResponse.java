package com.bonddesk.oms.dto;

/** A refreshed pair: a new access token and the rotated refresh token that replaces the one just used. */
public record TokenResponse(String accessToken, String refreshToken, String tokenType, long expiresInSeconds) {
}
