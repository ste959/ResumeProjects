package com.bonddesk.oms.fixedincome;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.fixedincome.dto.RfqDtos.CreateRfqRequest;
import com.bonddesk.oms.fixedincome.dto.RfqDtos.RfqExecutionView;
import com.bonddesk.oms.fixedincome.dto.RfqDtos.RfqView;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Fixed-income request-for-quote desk. Bonds trade OTC by dealer quote, not on a lit book,
 * so this endpoint models that market structure: request a quote, receive firm dealer
 * prices off the real Treasury curve, and accept one to book the trade.
 */
@RestController
@RequestMapping("/api/rfq")
@Tag(name = "RFQ", description = "Fixed-income request-for-quote (dealer-quoted OTC trading)")
public class RfqController {

    private final RfqService rfq;
    private final YieldCurveService curve;

    public RfqController(RfqService rfq, YieldCurveService curve) {
        this.rfq = rfq;
        this.curve = curve;
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping
    @Operation(summary = "Request quotes on a bond from the dealer panel")
    public RfqView create(@Valid @RequestBody CreateRfqRequest req) {
        return RfqView.from(rfq.create(req));
    }

    @GetMapping
    @Operation(summary = "List recent RFQs")
    public List<RfqView> list() {
        return rfq.list().stream().map(RfqView::from).toList();
    }

    @GetMapping("/{id}")
    @Operation(summary = "Fetch a single RFQ with its dealer quotes")
    public RfqView get(@PathVariable String id) {
        return RfqView.from(rfq.get(id));
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{id}/accept")
    @Operation(summary = "Accept a quote (best execution by default, or a named dealer) and book the trade")
    public RfqExecutionView accept(@PathVariable String id,
                                   @RequestParam(required = false) String dealer) {
        Order booked = rfq.accept(id, dealer);
        return RfqExecutionView.from(id, booked);
    }

    @GetMapping("/curve")
    @Operation(summary = "The current benchmark yield curve the desk prices off")
    public YieldCurve curve() {
        return curve.current();
    }
}
