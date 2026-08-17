package com.bonddesk.oms.dto;

import com.bonddesk.oms.exception.BadRequestException;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** The opaque pagination cursor round-trips at full precision and rejects tampered input as a 400. */
class CursorTest {

    @Test
    void roundTripsCreatedAtAndIdAtFullPrecision() {
        Cursor original = new Cursor(Instant.parse("2026-08-17T14:30:00.123456Z"), 9876543210L);
        Cursor decoded = Cursor.decode(original.encode());
        assertThat(decoded.createdAt()).isEqualTo(original.createdAt());
        assertThat(decoded.id()).isEqualTo(original.id());
    }

    @Test
    void rejectsAMalformedCursor() {
        assertThatThrownBy(() -> Cursor.decode("not-a-valid-cursor!!"))
                .isInstanceOf(BadRequestException.class);
    }

    @Test
    void rejectsAWellFormedBase64WithoutTheSeparator() {
        String noSeparator = java.util.Base64.getUrlEncoder().withoutPadding()
                .encodeToString("garbage".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        assertThatThrownBy(() -> Cursor.decode(noSeparator)).isInstanceOf(BadRequestException.class);
    }
}
