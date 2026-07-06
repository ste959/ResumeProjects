package com.bonddesk.oms.controller;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.dto.PositionResponse;
import com.bonddesk.oms.equities.EquityMarketDataService;
import com.bonddesk.oms.equities.EquityQuote;
import com.bonddesk.oms.service.PositionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/** Portfolio holdings, updated in real time as fills arrive and marked with live prices. */
@RestController
@RequestMapping("/api/portfolios")
@Tag(name = "Positions", description = "Portfolio holdings with live mark-to-market")
public class PositionController {

    private final PositionService positions;
    private final EquityMarketDataService equityMarketData;

    public PositionController(PositionService positions, EquityMarketDataService equityMarketData) {
        this.positions = positions;
        this.equityMarketData = equityMarketData;
    }

    @GetMapping("/{portfolio}/positions")
    @Operation(summary = "List a portfolio's positions with mark-to-market value")
    public List<PositionResponse> positions(@PathVariable String portfolio) {
        return positions.forPortfolio(portfolio).stream()
                .map(p -> PositionResponse.from(p, liveMark(p)))
                .toList();
    }

    /** Live mark for equities (feed mid, else last trade); null for bonds (use indicative price). */
    private BigDecimal liveMark(Position p) {
        Security s = p.getSecurity();
        if (s.getAssetClass() != AssetClass.EQUITY || s.getTicker() == null) {
            return null;
        }
        EquityQuote q = equityMarketData.quote(s.getTicker());
        if (q != null && q.bid() != null && q.ask() != null
                && q.bid().signum() > 0 && q.ask().signum() > 0) {
            return q.bid().add(q.ask()).divide(BigDecimal.valueOf(2), 4, RoundingMode.HALF_UP);
        }
        return equityMarketData.lastPrice(s.getTicker());
    }
}
