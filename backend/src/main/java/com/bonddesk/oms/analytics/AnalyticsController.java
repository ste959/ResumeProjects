package com.bonddesk.oms.analytics;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** Reporting / analytics endpoints backed by hand-written SQL (see {@link AnalyticsService}). */
@RestController
@RequestMapping("/api/analytics")
@Tag(name = "Analytics", description = "Desk reporting & transaction cost analysis (raw SQL)")
public class AnalyticsController {

    private final AnalyticsService analytics;

    public AnalyticsController(AnalyticsService analytics) {
        this.analytics = analytics;
    }

    @GetMapping("/desk-summary")
    @Operation(summary = "Order counts, working/rejected, filled notional and fill rate")
    public DeskSummary deskSummary() {
        return analytics.deskSummary();
    }

    @GetMapping("/execution-quality")
    @Operation(summary = "TCA: avg fill vs. benchmark and slippage (bps) by security and side")
    public List<ExecutionQuality> executionQuality() {
        return analytics.executionQuality();
    }

    @GetMapping("/top-securities")
    @Operation(summary = "Highest-volume securities by filled notional")
    public List<SecurityVolume> topSecurities(@RequestParam(defaultValue = "5") int limit) {
        return analytics.topSecuritiesByVolume(Math.clamp(limit, 1, 50));
    }

    @GetMapping("/daily-volume")
    @Operation(summary = "Daily traded volume with running cumulative total (window function)")
    public List<DailyVolume> dailyVolume() {
        return analytics.dailyVolume();
    }
}
