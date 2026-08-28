package com.bonddesk.oms.strategy;

import com.bonddesk.oms.strategy.StrategyDtos.CreateStrategyRequest;
import com.bonddesk.oms.strategy.StrategyDtos.ModifyStrategyRequest;
import com.bonddesk.oms.strategy.StrategyDtos.StrategyView;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** Launch and monitor trading strategies (execution algos + market making) on the live feed. */
@RestController
@RequestMapping("/api/strategies")
@Tag(name = "Strategies", description = "Execution algos + market making with live TCA")
public class StrategyController {

    private final StrategyService strategies;

    public StrategyController(StrategyService strategies) {
        this.strategies = strategies;
    }

    @GetMapping
    @Operation(summary = "List strategy runs with live P&L / inventory / TCA")
    public List<StrategyView> list() {
        return strategies.views();
    }

    @GetMapping("/{id}")
    @Operation(summary = "One strategy run")
    public StrategyView get(@PathVariable String id) {
        return strategies.view(id);
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping
    @Operation(summary = "Launch a strategy (TWAP/POV/ALMGREN_CHRISS or AVELLANEDA_STOIKOV)")
    public StrategyView create(@RequestBody CreateStrategyRequest request) {
        return strategies.view(strategies.create(request).id());
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{id}/stop")
    @Operation(summary = "Stop a running strategy")
    public StrategyView stop(@PathVariable String id) {
        return strategies.stop(id);
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{id}/pause")
    @Operation(summary = "Pause a running strategy (the runner skips it until resumed)")
    public StrategyView pause(@PathVariable String id) {
        return strategies.pause(id);
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{id}/resume")
    @Operation(summary = "Resume a paused strategy")
    public StrategyView resume(@PathVariable String id) {
        return strategies.resume(id);
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{id}/modify")
    @Operation(summary = "Modify a running strategy's tunable parameters (POV participation; maker gamma/quoteSize)")
    public StrategyView modify(@PathVariable String id, @RequestBody ModifyStrategyRequest request) {
        return strategies.modify(id, request);
    }
}
