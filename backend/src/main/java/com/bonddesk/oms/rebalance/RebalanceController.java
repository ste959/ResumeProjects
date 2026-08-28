package com.bonddesk.oms.rebalance;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;

/**
 * Equity rebalance endpoint: reads the research target book and routes the delta orders to
 * the paper venue. This is execution-infrastructure validation, not alpha deployment.
 *
 * <p>The whole controller is gated on {@code oms.rebalance.enabled} (default false) so it is
 * not even registered unless explicitly switched on, and {@code dryRun} defaults to
 * {@code true} so the naive call previews the plan without routing anything.
 */
@RestController
@RequestMapping("/api/equity")
@ConditionalOnProperty(prefix = "oms.rebalance", name = "enabled", havingValue = "true")
@Tag(name = "Equity Rebalance", description = "Target-book → delta orders → paper venue (plumbing validation)")
public class RebalanceController {

    private final RebalanceService rebalance;
    private final RebalanceProperties props;

    public RebalanceController(RebalanceService rebalance, RebalanceProperties props) {
        this.rebalance = rebalance;
        this.props = props;
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/rebalance")
    @Operation(summary = "Rebalance a paper equity book toward the research target book (dry run by default)")
    public RebalanceResult rebalance(
            @RequestParam(required = false) BigDecimal grossCapital,
            @RequestParam(required = false) String portfolio,
            @RequestParam(defaultValue = "true") boolean dryRun) {
        BigDecimal capital = grossCapital != null ? grossCapital : props.getGrossCapital();
        String book = (portfolio != null && !portfolio.isBlank()) ? portfolio : props.getPortfolio();
        return rebalance.execute(capital, book, dryRun);
    }
}
