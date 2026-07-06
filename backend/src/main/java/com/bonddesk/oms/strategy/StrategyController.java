package com.bonddesk.oms.strategy;

import com.bonddesk.oms.strategy.StrategyDtos.CreateStrategyRequest;
import com.bonddesk.oms.strategy.StrategyDtos.StrategyView;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
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

    @PostMapping
    @Operation(summary = "Launch a strategy (TWAP/POV/ALMGREN_CHRISS or AVELLANEDA_STOIKOV)")
    public StrategyView create(@RequestBody CreateStrategyRequest request) {
        return strategies.view(strategies.create(request).id());
    }

    @PostMapping("/{id}/stop")
    @Operation(summary = "Stop a running strategy")
    public StrategyView stop(@PathVariable String id) {
        return strategies.stop(id);
    }
}
