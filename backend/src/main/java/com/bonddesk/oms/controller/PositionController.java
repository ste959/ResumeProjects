package com.bonddesk.oms.controller;

import com.bonddesk.oms.dto.PositionResponse;
import com.bonddesk.oms.service.PositionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** Portfolio holdings, updated in real time as fills arrive. */
@RestController
@RequestMapping("/api/portfolios")
@Tag(name = "Positions", description = "Portfolio holdings with live mark-to-market")
public class PositionController {

    private final PositionService positions;

    public PositionController(PositionService positions) {
        this.positions = positions;
    }

    @GetMapping("/{portfolio}/positions")
    @Operation(summary = "List a portfolio's positions with mark-to-market value")
    public List<PositionResponse> positions(@PathVariable String portfolio) {
        return positions.forPortfolio(portfolio).stream().map(PositionResponse::from).toList();
    }
}
