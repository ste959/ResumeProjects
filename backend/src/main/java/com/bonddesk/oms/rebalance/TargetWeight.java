package com.bonddesk.oms.rebalance;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

import java.math.BigDecimal;

/**
 * One name in a research target book: its desired portfolio weight and the reference
 * price the research sized it at. Weights are dollar-neutral (they sum to ≈ 0) and
 * unit-gross (Σ|weight| ≈ 1), so a name's dollar allocation is {@code weight * grossCapital}.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record TargetWeight(
        String symbol,
        BigDecimal weight,
        BigDecimal price) {
}
