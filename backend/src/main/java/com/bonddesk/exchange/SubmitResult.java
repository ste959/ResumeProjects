package com.bonddesk.exchange;

import java.util.List;

/** The outcome of submitting an order: the assigned id, a status, any trades, and what rested. */
public record SubmitResult(
        long orderId,
        Status status,
        String reason,
        List<Trade> trades,
        long filledQty,
        long restingQty
) {
    public enum Status {
        FILLED,             // fully matched on entry
        PARTIALLY_FILLED,   // partly matched, remainder cancelled (IOC / MARKET)
        RESTING,            // remainder rests on the book (LIMIT GTC), possibly after a partial fill
        CANCELLED,          // took nothing and did not rest (IOC / MARKET with no liquidity)
        REJECTED            // validation, post-only-would-cross, or FOK-unfillable
    }

    public boolean accepted() {
        return status != Status.REJECTED;
    }
}
