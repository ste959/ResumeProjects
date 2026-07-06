package com.bonddesk.oms.backtest;

import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestResult;
import com.bonddesk.oms.backtest.dto.BacktestDtos.CapacityPoint;
import com.bonddesk.oms.backtest.dto.BacktestDtos.CapacityRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.RobustnessPoint;
import com.bonddesk.oms.backtest.dto.BacktestDtos.RobustnessRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.SessionView;
import com.bonddesk.oms.backtest.dto.BacktestDtos.SyntheticRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.SyntheticResult;
import com.bonddesk.oms.market.CoinbaseProperties;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

/**
 * Backtesting desk: replay a recorded L2 session through a strategy and get execution
 * quality + P&L. Reuses the live execution engine, so backtest and live share the code.
 */
@RestController
@RequestMapping("/api/backtest")
@Tag(name = "Backtest", description = "Replay recorded L2 order-book data through the live execution engine")
public class BacktestController {

    private final BacktestService backtest;
    private final SyntheticMarketGenerator synthetic;
    private final CoinbaseProperties props;

    public BacktestController(BacktestService backtest, SyntheticMarketGenerator synthetic,
                              CoinbaseProperties props) {
        this.backtest = backtest;
        this.synthetic = synthetic;
        this.props = props;
    }

    @PostMapping
    @Operation(summary = "Replay a strategy against a recorded L2 session")
    public BacktestResult run(@RequestBody BacktestRequest req) {
        return backtest.run(req);
    }

    @PostMapping("/capacity")
    @Operation(summary = "Sweep a strategy across order sizes — the capacity curve (cost grows with size)")
    public List<CapacityPoint> capacity(@RequestBody CapacityRequest req) {
        return backtest.capacity(req);
    }

    @PostMapping("/robustness")
    @Operation(summary = "Replay a strategy across market-condition scenarios — robustness vs. overfitting")
    public List<RobustnessPoint> robustness(@RequestBody RobustnessRequest req) {
        return backtest.robustness(req);
    }

    @PostMapping("/synthetic")
    @Operation(summary = "Generate a synthetic market with a known signal — a replayable session for ML validation")
    public SyntheticResult synthetic(@RequestBody SyntheticRequest req) {
        return synthetic.generate(req);
    }

    @GetMapping("/sessions")
    @Operation(summary = "List recorded L2 capture sessions available to replay")
    public List<SessionView> sessions() {
        Path dir = Path.of(props.getL2CaptureDir());
        if (!Files.isDirectory(dir)) {
            return List.of();
        }
        try (Stream<Path> files = Files.list(dir)) {
            return files.filter(p -> p.getFileName().toString().matches("l2-.*\\.csv"))
                    .sorted((a, b) -> b.getFileName().toString().compareTo(a.getFileName().toString()))
                    .map(BacktestController::describe)
                    .toList();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    private static SessionView describe(Path file) {
        String name = file.getFileName().toString();
        String date = name.replaceFirst("^l2-", "").replaceFirst("\\.csv$", "");
        long rows = 0;
        long bytes = 0;
        try (Stream<String> lines = Files.lines(file)) {
            rows = Math.max(0, lines.count() - 1); // minus header
            bytes = Files.size(file);
        } catch (IOException ignored) {
            // best-effort metadata
        }
        return new SessionView(date, name, rows, bytes);
    }
}
