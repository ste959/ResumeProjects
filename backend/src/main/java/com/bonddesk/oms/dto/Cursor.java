package com.bonddesk.oms.dto;

import com.bonddesk.oms.exception.BadRequestException;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.Base64;

/**
 * The keyset position for blotter pagination: the {@code (createdAt, id)} of the last row a client has
 * seen. Orders sort by {@code createdAt DESC, id DESC}, so the next page is everything strictly "before"
 * this point — {@code id} breaks ties when two orders share a timestamp, which keeps paging stable.
 *
 * <p>Encoded as an opaque Base64 token so clients treat it as a handle, not a value to construct. The
 * full-precision {@link Instant} is preserved so the keyset comparison matches the stored value exactly.
 */
public record Cursor(Instant createdAt, long id) {

    private static final String SEP = "|";

    public String encode() {
        String raw = createdAt.toString() + SEP + id;
        return Base64.getUrlEncoder().withoutPadding().encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    /** Decode a client-supplied cursor, rejecting anything malformed as a 400 rather than a 500. */
    public static Cursor decode(String token) {
        try {
            String raw = new String(Base64.getUrlDecoder().decode(token), StandardCharsets.UTF_8);
            int sep = raw.lastIndexOf(SEP);
            if (sep < 0) {
                throw new BadRequestException("Malformed pagination cursor");
            }
            Instant createdAt = Instant.parse(raw.substring(0, sep));
            long id = Long.parseLong(raw.substring(sep + 1));
            return new Cursor(createdAt, id);
        } catch (IllegalArgumentException | DateTimeParseException e) {
            throw new BadRequestException("Malformed pagination cursor");
        }
    }
}
