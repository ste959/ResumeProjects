package com.bonddesk.oms.risk.dto;

import java.util.List;
import java.util.Map;

/** API view models for the portfolio risk engine. */
public final class RiskDtos {

    private RiskDtos() {
    }

    /** Portfolio P&L under a named stress scenario. */
    public record ScenarioPnl(String scenario, double pnl, String description) {
    }

    /**
     * Aggregate risk for a portfolio: exposures, interest-rate risk (DV01), a parametric
     * 1-day 95% VaR (diversified vs. undiversified), and scenario stress including a
     * correlated risk-off shock. Risk is aggregate and by factor, not per-line-item.
     */
    public record PortfolioRiskReport(
            String portfolio,
            int positions,
            double grossNotional,
            double netNotional,
            double fixedIncomeNotional,
            double equityNotional,
            double aggregateDv01,      // $ P&L per 1bp parallel rate move
            double corporateDv01,      // spread-sensitive subset
            double var95Diversified,
            double var95Undiversified,
            double diversificationBenefit,
            Map<String, Double> sectorExposure,
            List<ScenarioPnl> scenarios
    ) {
    }
}
