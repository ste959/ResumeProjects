package com.bonddesk.oms.rebalance;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.math.BigDecimal;
import java.util.List;

/**
 * A research-produced target book: the desired dollar-neutral, unit-gross weight for each
 * name as of a given date. This is the <em>input</em> the rebalance path consumes to
 * generate delta orders — it is execution-plumbing validation, not an alpha signal (the
 * research found no edge).
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record TargetBook(
        String asOf,
        String strategy,
        BigDecimal grossLong,
        BigDecimal grossShort,
        List<TargetWeight> names) {
}
