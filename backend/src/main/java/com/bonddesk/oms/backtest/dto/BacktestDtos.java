package com.bonddesk.oms.backtest.dto;

import java.time.Instant;
import java.util.List;

/** API view models for the backtesting engine. */
public final class BacktestDtos {

    private BacktestDtos() {
    }

    /**
     * Trading costs, all optional (sensible defaults applied). Maker fee can be negative
     * (a rebate). Regulatory fees and borrow matter mostly for equities; impactCoef scales
     * the square-root market-impact law.
     */
    public record Costs(
            Double takerFeeBps,
            Double makerFeeBps,        // negative = rebate
            Double commissionBps,
            Double regFeeBps,          // e.g. SEC/FINRA on equity sells
            Double borrowBpsPerYear,   // financing on short inventory
            Double impactCoef          // bps of impact at 100% participation (sqrt law)
    ) {
    }

    /** Runtime risk limits; a breach halts trading and flattens the position (kill-switch). */
    public record RiskLimits(
            Double maxDrawdownUsd,
            Double maxLossUsd,
            Double maxPositionSize
    ) {
    }

    /**
     * A counterfactual market-condition transform applied to the recorded stream during replay,
     * to test a strategy's robustness across regimes. All optional (default = no change).
     */
    public record Scenario(
            Double volScale,        // scale price volatility (>1 = more volatile)
            Double spreadScale,     // scale the bid/ask spread
            Double liquidityScale,  // scale resting size (thin vs. thick book)
            Double driftBpsPerMin,  // impose a trend
            Double shockBps,        // one-off price jump
            Long shockAtSecond      // when the shock hits (seconds into the session)
    ) {
    }

    /**
     * A backtest request: which recorded session (product + optional date, else latest),
     * which strategy to replay, its parameters, decision latency, and cost assumptions.
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
            Long latencyMs,        // decision-to-market latency (order + cancel); 0 = none
            String date,           // capture date (yyyy-MM-dd); null = latest file
            Costs costs,           // trading costs; null = defaults
            RiskLimits riskLimits, // runtime kill-switches; null = none
            Scenario scenario      // counterfactual market transform; null = replay as recorded
    ) {
    }

    public record FillView(Instant time, String side, double price, double size, String liquidity) {
    }

    /**
     * The result of replaying a strategy against recorded L2: execution quality
     * (implementation shortfall), microstructure diagnostics (markouts), gross and
     * after-cost P&L, and the cost breakdown, plus replay metadata.
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
            double totalPnl,          // gross, before costs
            double feeCostUsd,
            double impactCostUsd,
            double financingCostUsd,
            double netPnl,            // after fees + impact + financing
            double feeBps,
            double impactBps,
            double allInCostBps,      // fees + impact + financing, per notional
            double maxDrawdownUsd,    // observed peak-to-trough of mark-to-market P&L
            boolean halted,           // did a risk kill-switch fire?
            String haltReason,
            int numFills,
            int makerFills,
            int takerFills,
            double avgMarkoutBps1s,
            double avgMarkoutBps10s,
            long eventsProcessed,
            long ticks,
            Instant sessionStart,
            Instant sessionEnd,
            String note,
            List<FillView> fills
    ) {
    }

    /** Request to sweep a strategy across order sizes and build a capacity curve. */
    public record CapacityRequest(
            String product,
            String strategyType,
            String side,
            Integer slices,
            List<Double> sizes,
            Long tickMs,
            Long latencyMs,
            String date,
            Costs costs
    ) {
    }

    /** One point on the capacity curve: how the all-in cost of trading grows with size. */
    public record CapacityPoint(
            double size,
            double executedSize,
            double grossShortfallBps,
            double feeBps,
            double impactBps,
            double allInCostBps,
            double netPnl
    ) {
    }

    public record NamedScenario(String label, Scenario scenario) {
    }

    /** Sweep a strategy across market-condition scenarios to measure robustness. */
    public record RobustnessRequest(
            String product,
            String strategyType,
            String side,
            Double size,
            Integer slices,
            Double quoteSize,
            Long tickMs,
            Long latencyMs,
            String date,
            Costs costs,
            List<NamedScenario> scenarios
    ) {
    }

    /** One row of the robustness sweep: how the strategy fared under a named regime. */
    public record RobustnessPoint(
            String label,
            double executedSize,
            double shortfallBps,
            double allInCostBps,
            double netPnl,
            double avgMarkoutBps1s,
            double maxDrawdownUsd,
            boolean halted
    ) {
    }

    public record SessionView(String date, String file, long rows, long sizeBytes) {
    }

    /**
     * Parameters for a synthetic market. {@code imbalanceAlpha} injects a <em>known</em> signal:
     * the book imbalance is skewed toward the next mid move with this strength, so a model can be
     * validated against ground truth (alpha &gt; 0 → recoverable signal; alpha = 0 → pure noise,
     * a false-positive check). Written as a replayable session named {@code label}.
     */
    public record SyntheticRequest(
            String label,
            Integer durationSeconds,
            Long tickMs,
            Double midStart,
            Double volBps,          // per-tick price volatility, in bps
            Double driftBpsPerMin,
            Double spreadBps,
            Integer depthLevels,
            Double levelSize,
            Integer tradesPerTick,
            Double imbalanceAlpha,  // strength of the planted imbalance→return signal
            Long seed
    ) {
    }

    public record SyntheticResult(
            String label,
            String product,
            String file,
            long events,
            int ticks,
            double injectedAlpha
    ) {
    }
}
