package com.bonddesk.oms.rates;

import com.bonddesk.oms.rates.RatesDtos.RfqView;
import com.bonddesk.oms.rates.RatesDtos.ShockRequest;
import com.bonddesk.oms.rates.RatesDtos.Snapshot;
import com.bonddesk.oms.rates.RatesDtos.SubmitRfqRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** The live rates desk: snapshot + submit an RFQ + shock the curve. Market data streams over /ws/rates. */
@RestController
@RequestMapping("/api/rates")
@Tag(name = "Rates", description = "Live rates desk: curve, dealer RFQ auctions, book risk, P&L attribution")
public class RatesController {

    private final RatesSimulation sim;

    public RatesController(RatesSimulation sim) {
        this.sim = sim;
    }

    @GetMapping("/snapshot")
    @Operation(summary = "Current rates-desk snapshot (curve, last RFQ, dealers, book, analytics)")
    public Snapshot snapshot() {
        return sim.snapshot();
    }

    @PostMapping("/rfq")
    @Operation(summary = "Send an RFQ into the dealer market and get the auction back")
    public RfqView submitRfq(@RequestBody SubmitRfqRequest request) {
        return sim.submitRfq(request);
    }

    @PostMapping("/shock")
    @Operation(summary = "Apply a parallel + slope curve shock (bps) and reprice the book")
    public Snapshot shock(@RequestBody ShockRequest request) {
        return sim.shock(request);
    }
}
