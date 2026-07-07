package com.bonddesk.oms.strategy;

import com.bonddesk.oms.exception.BadRequestException;
import com.bonddesk.oms.exception.NotFoundException;
import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.MarketDataService;
import com.bonddesk.oms.strategy.StrategyDtos.CreateStrategyRequest;
import com.bonddesk.oms.strategy.StrategyDtos.ModifyStrategyRequest;
import com.bonddesk.oms.strategy.StrategyDtos.StrategyView;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/** Creates, tracks and reports strategy runs; the runner drives them each tick. */
@Service
public class StrategyService {

    private final MarketDataService marketData;
    private final Clock clock;
    private final Map<String, StrategyRun> runs = new ConcurrentHashMap<>();

    public StrategyService(MarketDataService marketData, Clock clock) {
        this.marketData = marketData;
        this.clock = clock;
    }

    public StrategyRun create(CreateStrategyRequest req) {
        if (req.product() == null || req.type() == null) {
            throw new BadRequestException("type and product are required");
        }
        LiveOrderBook book = marketData.book(req.product());
        double mid = book.mid() != null ? book.mid().doubleValue() : 0.0;

        Strategy strategy = build(req);
        StrategyRun run = new StrategyRun(strategy.type(), req.product(), strategy, clock.instant());
        run.setArrivalMid(mid);
        run.setLastTradeSeq(marketData.currentTradeSeq());
        if (strategy instanceof ExecutionStrategy) {
            run.setParent(buy(req) ? "BUY" : "SELL", req.size() == null ? 0 : req.size());
        }
        runs.put(run.id(), run);
        return run;
    }

    private Strategy build(CreateStrategyRequest r) {
        String type = r.type().toUpperCase();
        return switch (type) {
            case "TWAP" -> new TwapExecution(buy(r), size(r), slices(r));
            case "POV" -> new PovExecution(buy(r), size(r), slices(r), or(r.participation(), 0.1));
            case "ALMGREN_CHRISS" -> new AlmgrenChrissExecution(buy(r), size(r), slices(r), or(r.kappa(), 0.3));
            case "AVELLANEDA_STOIKOV" -> new AvellanedaStoikovMaker(
                    or(r.gamma(), 0.3), or(r.kappa(), 1.5), or(r.tau(), 60.0), or(r.quoteSize(), 0.05));
            default -> throw new BadRequestException("unknown strategy type: " + r.type());
        };
    }

    public List<StrategyRun> activeRuns() {
        return runs.values().stream().filter(StrategyRun::isActive).toList();
    }

    public List<StrategyView> views() {
        return runs.values().stream()
                .sorted(Comparator.comparing(StrategyRun::createdAt).reversed())
                .map(this::view)
                .toList();
    }

    public StrategyView view(String id) {
        return view(Optional.ofNullable(runs.get(id))
                .orElseThrow(() -> new NotFoundException("no strategy run " + id)));
    }

    public StrategyView stop(String id) {
        StrategyRun run = require(id);
        run.setStatus("STOPPED");
        return view(run);
    }

    /** Pause a running strategy — the runner skips it (only RUNNING runs are stepped) until resumed. */
    public StrategyView pause(String id) {
        StrategyRun run = require(id);
        if ("RUNNING".equals(run.status())) {
            run.setStatus("PAUSED");
        }
        return view(run);
    }

    /** Resume a paused strategy. */
    public StrategyView resume(String id) {
        StrategyRun run = require(id);
        if ("PAUSED".equals(run.status())) {
            run.setStatus("RUNNING");
        }
        return view(run);
    }

    /**
     * Modify tunable parameters of a running strategy in place. Applies only the fields relevant to
     * the run's type (participation for POV; gamma/quoteSize for the maker); others are ignored. The
     * targeted fields are volatile, so the change is picked up by the runner on its next tick.
     */
    public StrategyView modify(String id, ModifyStrategyRequest req) {
        StrategyRun run = require(id);
        Strategy s = run.strategy();
        if (s instanceof PovExecution pov && req.participation() != null) {
            pov.setParticipation(clamp(req.participation(), 1e-4, 1.0));
        }
        if (s instanceof AvellanedaStoikovMaker mm) {
            if (req.gamma() != null) {
                mm.setGamma(clamp(req.gamma(), 1e-3, 100.0));
            }
            if (req.quoteSize() != null) {
                mm.setQuoteSize(Math.max(1e-6, req.quoteSize()));
            }
        }
        run.touch(clock.instant());
        return view(run);
    }

    private StrategyRun require(String id) {
        StrategyRun run = runs.get(id);
        if (run == null) {
            throw new NotFoundException("no strategy run " + id);
        }
        return run;
    }

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    private StrategyView view(StrategyRun run) {
        double mark = markPrice(run.product());
        PnlBook book = run.book();
        double realized = book.realized();
        double unrealized = book.unrealized(mark);

        Double execSize = null, avgExec = null, shortfall = null, parentSize = null;
        if (run.parentSide() != null) {
            parentSize = run.parentSize();
            execSize = run.executedSize();
            if (run.executedSize() > 0) {
                avgExec = run.executedNotional() / run.executedSize();
                double sign = "BUY".equals(run.parentSide()) ? 1.0 : -1.0;
                shortfall = run.arrivalMid() > 0
                        ? sign * (avgExec - run.arrivalMid()) / run.arrivalMid() * 1e4 : 0.0;
            }
        }

        return new StrategyView(
                run.id(), run.type(), run.product(), run.status(), run.createdAt(), run.updatedAt(),
                round(book.position(), 6), round(book.avgCost(), 2), round(mark, 2),
                round(realized, 2), round(unrealized, 2), round(realized + unrealized, 2),
                book.fills().size(),
                run.parentSide(), round(parentSize, 6), round(execSize, 6), round(avgExec, 2),
                round(run.parentSide() != null ? run.arrivalMid() : null, 2), round(shortfall, 2),
                round(run.quoteBid(), 2), round(run.quoteAsk(), 2));
    }

    private double markPrice(String product) {
        LiveOrderBook book = marketData.book(product);
        return book.mid() != null ? book.mid().doubleValue() : 0.0;
    }

    // ---- request helpers ----
    private static boolean buy(CreateStrategyRequest r) { return !"SELL".equalsIgnoreCase(r.side()); }
    private static double size(CreateStrategyRequest r) {
        if (r.size() == null || r.size() <= 0) throw new BadRequestException("size must be positive");
        return r.size();
    }
    private static int slices(CreateStrategyRequest r) { return r.slices() == null ? 20 : Math.max(1, r.slices()); }
    private static double or(Double v, double d) { return v == null ? d : v; }
    private static Double round(Double v, int dp) {
        if (v == null) return null;
        double f = Math.pow(10, dp);
        return Math.round(v * f) / f;
    }
    private static double round(double v, int dp) {
        double f = Math.pow(10, dp);
        return Math.round(v * f) / f;
    }
}
