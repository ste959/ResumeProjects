package com.bonddesk.oms.strategy;

import java.time.Instant;

/** Request/response models for the strategy engine. */
public final class StrategyDtos {

    private StrategyDtos() {
    }

    /**
     * Launch a strategy. Fields are interpreted per {@code type}:
     * <ul>
     *   <li>execution (TWAP/POV/ALMGREN_CHRISS): side, size, slices, participation, kappa</li>
     *   <li>market maker (AVELLANEDA_STOIKOV): gamma, kappa, tau, quoteSize</li>
     * </ul>
     */
    public record CreateStrategyRequest(
            String type,
            String product,
            String side,
            Double size,
            Integer slices,
            Double participation,
            Double kappa,
            Double gamma,
            Double tau,
            Double quoteSize
    ) {}

    public record StrategyView(
            String id,
            String type,
            String product,
            String status,
            Instant createdAt,
            Instant updatedAt,
            double position,
            double avgCost,
            double markPrice,
            double realizedPnl,
            double unrealizedPnl,
            double totalPnl,
            int numFills,
            // execution TCA (null for MM)
            String parentSide,
            Double parentSize,
            Double executedSize,
            Double avgExecPrice,
            Double arrivalMid,
            Double implementationShortfallBps,
            // maker state (0 for execution)
            double quoteBid,
            double quoteAsk
    ) {}
}
