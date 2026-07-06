package com.bonddesk.oms.backtest.dto;

import java.time.Instant;
import java.util.List;

/** API view models for the backtesting engine. */
public final class BacktestDtos {

    private BacktestDtos() {
    }

    /**
     * A backtest request: which recorded session (product + optional date, else latest),
     * which strategy to replay, and its parameters.
     */
    public record BacktestRequest(
            String product,
            String strategyType,   // TWAP | POV | ALMGREN_CHRISS | AVELLANEDA_STOIKOV
            String side,           // BUY | SELL (execution algos)
            Double size,
            Integer slices,
            Double participation,  // POV
            Double kappa,          // Almgren–Chriss / Avellaneda–Stoikov
            Double gamma,          // Avellaneda–Stoikov risk aversion
            Double tau,            // Avellaneda–Stoikov horizon
            Double quoteSize,      // Avellaneda–Stoikov quote size
            Long tickMs,           // strategy tick cadence in virtual time
            String date            // capture date (yyyy-MM-dd); null = latest file
    ) {
    }

    public record FillView(Instant time, String side, double price, double size, String liquidity) {
    }

    /**
     * The result of replaying a strategy against recorded L2: execution quality
     * (implementation shortfall vs. arrival mid) and P&L, plus replay metadata.
     */
    public record BacktestResult(
            String product,
            String strategyType,
            String side,
            double requestedSize,
            double executedSize,
            double avgExecPrice,
            double arrivalMid,
            double implementationShortfallBps,
            double finalMark,
            double finalPosition,
            double realizedPnl,
            double unrealizedPnl,
            double totalPnl,
            int numFills,
            int makerFills,
            int takerFills,
            double avgMarkoutBps1s,   // adverse selection: fill P&L 1s later (negative = picked off)
            double avgMarkoutBps10s,
            long eventsProcessed,
            long ticks,
            Instant sessionStart,
            Instant sessionEnd,
            String note,
            List<FillView> fills
    ) {
    }

    public record SessionView(String date, String file, long rows, long sizeBytes) {
    }
}
