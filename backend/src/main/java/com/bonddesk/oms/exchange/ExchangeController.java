package com.bonddesk.oms.exchange;

import com.bonddesk.oms.exchange.ExchangeDtos.AnalyticsView;
import com.bonddesk.oms.exchange.ExchangeDtos.PlaceRequest;
import com.bonddesk.oms.exchange.ExchangeDtos.PlaceResponse;
import com.bonddesk.oms.exchange.ExchangeDtos.Snapshot;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** Order entry + a snapshot fallback for the live matching engine. Market data streams over /ws/exchange. */
@RestController
@RequestMapping("/api/exchange")
@Tag(name = "Exchange", description = "Live matching engine: place/cancel orders + market-data snapshot")
public class ExchangeController {

    private final ExchangeSimulation sim;

    public ExchangeController(ExchangeSimulation sim) {
        this.sim = sim;
    }

    @GetMapping("/snapshot")
    @Operation(summary = "Current market-data snapshot (book + trades + engine stats)")
    public Snapshot snapshot() {
        return sim.snapshot();
    }

    @GetMapping("/analytics")
    @Operation(summary = "Market-maker analytics: P&L attribution, latency-by-match-depth, and the fill log")
    public AnalyticsView analytics() {
        return sim.analytics();
    }

    @PostMapping("/orders")
    @Operation(summary = "Place an order into the matching engine (as participant YOU)")
    public PlaceResponse place(@RequestBody PlaceRequest request) {
        return sim.place(request);
    }

    @PostMapping("/orders/{id}/cancel")
    @Operation(summary = "Cancel a resting order")
    public Map<String, Object> cancel(@PathVariable long id) {
        return Map.of("orderId", id, "cancelled", sim.cancel(id));
    }
}
