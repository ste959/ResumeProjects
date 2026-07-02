package com.bonddesk.risk;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Read-only risk view built from the consumed order-event stream. */
@RestController
@RequestMapping("/api/risk")
public class RiskController {

    private final RiskAggregator aggregator;

    public RiskController(RiskAggregator aggregator) {
        this.aggregator = aggregator;
    }

    @GetMapping("/summary")
    public DeskRiskSummary summary() {
        return aggregator.summary();
    }
}
