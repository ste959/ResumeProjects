package com.bonddesk.oms.dto;

import java.util.List;

/**
 * A keyset-paginated page. {@code nextCursor} is an opaque token the client passes back to fetch the
 * following page (null when there are no more rows). Keyset — not offset — pagination is used so paging
 * stays O(page size) no matter how deep the client goes, and can't skip or duplicate rows when new
 * orders arrive between requests.
 *
 * @param content    the rows in this page
 * @param nextCursor token for the next page, or null at the end
 * @param size       the page size that was applied (after clamping)
 * @param hasMore     whether another page exists
 */
public record PagedResponse<T>(List<T> content, String nextCursor, int size, boolean hasMore) {
}
