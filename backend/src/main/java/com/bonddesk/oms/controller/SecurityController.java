package com.bonddesk.oms.controller;

import com.bonddesk.oms.dto.SecurityResponse;
import com.bonddesk.oms.service.SecurityService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** Bond reference data — what the order-ticket security picker reads. */
@RestController
@RequestMapping("/api/securities")
@Tag(name = "Securities", description = "Bond reference data (security master)")
public class SecurityController {

    private final SecurityService securities;

    public SecurityController(SecurityService securities) {
        this.securities = securities;
    }

    @GetMapping
    @Operation(summary = "List bonds, optionally filtered by sector")
    public List<SecurityResponse> list(@RequestParam(required = false) String sector) {
        return securities.list(sector).stream().map(SecurityResponse::from).toList();
    }

    @GetMapping("/{cusip}")
    @Operation(summary = "Fetch a single bond by CUSIP")
    public SecurityResponse get(@PathVariable String cusip) {
        return SecurityResponse.from(securities.get(cusip));
    }
}
