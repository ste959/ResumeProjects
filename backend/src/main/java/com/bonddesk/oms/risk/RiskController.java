package com.bonddesk.oms.risk;

import com.bonddesk.oms.risk.dto.RiskDtos.PortfolioRiskReport;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Portfolio risk analytics: aggregate DV01, factor exposures, parametric VaR, and scenario
 * stress across the multi-asset book. Distinct from the Kafka-fed desk-exposure risk service.
 */
@RestController
@RequestMapping("/api/risk")
@Tag(name = "Risk", description = "Aggregate portfolio risk: DV01, VaR, scenario stress")
public class RiskController {

    private final RiskEngine risk;

    public RiskController(RiskEngine risk) {
        this.risk = risk;
    }

    @GetMapping("/portfolio/{portfolio}")
    @Operation(summary = "Aggregate risk report for a portfolio (DV01, VaR, stress scenarios)")
    public PortfolioRiskReport portfolio(@PathVariable String portfolio) {
        return risk.compute(portfolio);
    }
}
