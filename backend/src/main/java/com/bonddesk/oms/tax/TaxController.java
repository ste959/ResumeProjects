package com.bonddesk.oms.tax;

import com.bonddesk.oms.tax.dto.TaxDtos.TaxReport;
import com.bonddesk.oms.tax.dto.TaxDtos.TaxRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Tax desk: turn a sequence of trades into an after-tax P&L, honouring lot method, holding
 * period, wash sales (securities only), and the tax regime (retail vs. §475(f) MTM). Feed it
 * a backtest's fills to see the tax drag on a strategy — the cost almost no backtest models.
 */
@RestController
@RequestMapping("/api/tax")
@Tag(name = "Tax", description = "Lot-level tax accounting: FIFO/HIFO, holding period, wash sales, §475(f) MTM")
public class TaxController {

    private final TaxEngine engine;

    public TaxController(TaxEngine engine) {
        this.engine = engine;
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping
    @Operation(summary = "Compute after-tax P&L for a trade sequence under a lot method and regime")
    public TaxReport compute(@RequestBody TaxRequest req) {
        return engine.compute(req);
    }
}
