package com.bonddesk.oms.dto;

import jakarta.validation.constraints.NotBlank;

/** Body for the refresh and logout endpoints: the opaque refresh token to rotate or revoke. */
public record RefreshRequest(@NotBlank String refreshToken) {
}
