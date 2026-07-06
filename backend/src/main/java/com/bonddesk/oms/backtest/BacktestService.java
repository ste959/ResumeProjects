package com.bonddesk.oms.backtest;

import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.BacktestResult;
import com.bonddesk.oms.backtest.dto.BacktestDtos.CapacityPoint;
import com.bonddesk.oms.backtest.dto.BacktestDtos.CapacityRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.Costs;
import com.bonddesk.oms.backtest.dto.BacktestDtos.FillView;
import com.bonddesk.oms.backtest.dto.BacktestDtos.NamedScenario;
import com.bonddesk.oms.backtest.dto.BacktestDtos.RiskLimits;
import com.bonddesk.oms.backtest.dto.BacktestDtos.RobustnessPoint;
import com.bonddesk.oms.backtest.dto.BacktestDtos.RobustnessRequest;
import com.bonddesk.oms.backtest.dto.BacktestDtos.Scenario;
import com.bonddesk.oms.exception.BadRequestException;
import com.bonddesk.oms.exception.NotFoundException;
import com.bonddesk.oms.market.CoinbaseProperties;
import com.bonddesk.oms.market.LiveOrderBook;
import com.bonddesk.oms.market.LiveOrderBook.Level;
import com.bonddesk.oms.strategy.AlmgrenChrissExecution;
import com.bonddesk.oms.strategy.AvellanedaStoikovMaker;
import com.bonddesk.oms.strategy.ExecutionModel;
import com.bonddesk.oms.strategy.Fill;
import com.bonddesk.oms.strategy.MarketState;
import com.bonddesk.oms.strategy.PnlBook;
import com.bonddesk.oms.strategy.PovExecution;
import com.bonddesk.oms.strategy.Strategy;
import com.bonddesk.oms.strategy.StrategyContext;
import com.bonddesk.oms.strategy.StrategyRun;
import com.bonddesk.oms.strategy.TwapExecution;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.stream.Stream;

/**
 * Replays a recorded full-depth L2 session and drives a strategy through it — reconstructing
 * the order book event-by-event over virtual time, ticking the strategy on a cadence, and
 * accounting P&L. Crucially it reuses the <em>live</em> execution seam ({@link Strategy},
 * {@link StrategyContext}, {@link com.bonddesk.oms.strategy.ExecutionModel} sweep,
 * {@link PnlBook}), so the exact code that trades live also runs in backtest.
 *
 * <p>Phase 1 (this class) establishes the replay spine with a sweep fill against real
 * recorded depth (honest multi-level slippage). The realistic microstructure fill model
 * (queue position, adverse selection, latency, our own market impact) layers on in later
 * phases — see MARKET-REALISM.md.
 */
@Service
public class BacktestService {

    private static final Logger log = LoggerFactory.getLogger(BacktestService.class);
    private static final int VOL_WINDOW = 60;

    private final CoinbaseProperties props;

    public BacktestService(CoinbaseProperties props) {
        this.props = props;
    }

    public BacktestResult run(BacktestRequest req) {
        if (req.product() == null || req.product().isBlank()) {
            throw new BadRequestException("product is required");
        }
        boolean buy = !"SELL".equalsIgnoreCase(req.side());
        Strategy strategy = build(req, buy);
        String product = req.product();
        long tickMs = req.tickMs() != null ? req.tickMs() : 500L;
        Path file = resolveFile(req.date());
        ScenarioTransform transform = buildTransform(req.scenario());

        LiveOrderBook book = new LiveOrderBook(product);
        StrategyRun run = null;
        Instant nextTick = null;
        Instant firstTs = null;
        Instant lastTs = null;
        boolean started = false;
        boolean tradingDone = false;
        boolean arrivalSet = false;
        Deque<Double> mids = new ArrayDeque<>();
        double volSinceTick = 0;
        double sessionVolume = 0;   // total traded volume — the ADV proxy for market impact
        long events = 0;
        long ticks = 0;

        // Decision-to-market latency: the fill model acts on the quote as it was
        // `latencyMs` ago. This captures order latency (a new quote posts late) and cancel
        // latency (the old quote lingers until it does) — how makers get run over in fast
        // moves. quoteHist holds {tsMillis, bid, ask, size} snapshots at each tick.
        long latencyMs = req.latencyMs() != null ? Math.max(0, req.latencyMs()) : 0;
        Deque<double[]> quoteHist = new ArrayDeque<>();

        // Passive (maker) queue-position state, per side: the currently-active (latency-lagged)
        // quote, how much size is ahead of us, reaching volume traded, and how much has filled.
        double lastActiveBid = -1;
        double lastActiveAsk = -1;
        double lastActiveSz = -1;
        double qBidPx = 0;
        double qAskPx = 0;
        double qSzBid = 0;
        double qSzAsk = 0;
        double queueAheadBid = 0;
        double queueAheadAsk = 0;
        double cumReachBid = 0;
        double cumReachAsk = 0;
        double filledBid = 0;
        double filledAsk = 0;

        // Markout (adverse-selection) state: for each fill, revisit the mid +1s and +10s
        // later. Each entry is {dueEpochMillis, fillPrice, sideSign(+1 buy / -1 sell)}.
        Deque<double[]> mk1s = new ArrayDeque<>();
        Deque<double[]> mk10s = new ArrayDeque<>();
        // Markouts are SIZE-WEIGHTED (a 100-unit fill must count 100x a 1-unit fill), so
        // moSum accumulates size*markout and moWt accumulates size; the average is the ratio.
        double moSum1s = 0;
        double moSum10s = 0;
        double moWt1s = 0;
        double moWt10s = 0;
        int lastFillCount = 0;

        // Runtime risk: track the mark-to-market high-water mark and drawdown; a breach trips
        // the kill-switch, flattens the position, and stops trading.
        RiskLimits limits = req.riskLimits();
        double peakPnl = 0;
        double maxDrawdown = 0;
        boolean halted = false;
        String haltReason = null;

        // Snapshot rows for one snapshot event share a sequence and are contiguous.
        List<Level> snapBids = new ArrayList<>();
        List<Level> snapAsks = new ArrayList<>();
        long snapSeq = Long.MIN_VALUE;
        boolean inSnap = false;

        try (BufferedReader r = Files.newBufferedReader(file)) {
            r.readLine(); // header
            String line;
            while ((line = r.readLine()) != null) {
                L2Event e = parse(line);
                if (e == null || !product.equals(e.product())) {
                    continue;
                }
                events++;
                if (transform != null) {
                    if (firstTs == null) {
                        transform.start(e.ts());
                    }
                    e = transform.apply(e); // counterfactual regime
                }
                if (firstTs == null) {
                    firstTs = e.ts();
                }
                lastTs = e.ts();
                if (run == null) {
                    run = new StrategyRun(strategy.type(), product, strategy, e.ts());
                }

                // Latency: the active quote the fill model uses is the one in force
                // `latencyMs` ago. When it changes, reset queue position at the new prices.
                // Skip entirely once halted — a stale quote must not re-activate and re-open
                // the position the kill-switch just flattened.
                if (!halted && !quoteHist.isEmpty()) {
                    long laggedMs = e.ts().toEpochMilli() - latencyMs;
                    double[] active = null;
                    for (double[] q : quoteHist) {
                        if (q[0] <= laggedMs) {
                            active = q;
                        } else {
                            break;
                        }
                    }
                    if (active != null && (active[1] != lastActiveBid || active[2] != lastActiveAsk
                            || active[3] != lastActiveSz)) {
                        qBidPx = active[1];
                        qAskPx = active[2];
                        qSzBid = active[3];
                        qSzAsk = active[3];
                        // Queue-ahead is the size at OUR EXACT level (time priority). Better
                        // levels are consumed by any trade that reaches us, so counting them
                        // (sizeAtOrBetter) over-states the queue and starves the fill.
                        queueAheadBid = book.sizeAt(true, BigDecimal.valueOf(qBidPx)).doubleValue();
                        queueAheadAsk = book.sizeAt(false, BigDecimal.valueOf(qAskPx)).doubleValue();
                        cumReachBid = 0;
                        cumReachAsk = 0;
                        filledBid = 0;
                        filledAsk = 0;
                        lastActiveBid = active[1];
                        lastActiveAsk = active[2];
                        lastActiveSz = active[3];
                    }
                    while (quoteHist.size() > 2 && quoteHist.peekFirst()[0] < laggedMs - 5000) {
                        quoteHist.pollFirst();
                    }
                }

                if (e.isSnapshot()) {
                    if (!inSnap || e.seq() != snapSeq) {
                        if (inSnap) {
                            book.resetTo(snapBids, snapAsks);
                        }
                        snapBids = new ArrayList<>();
                        snapAsks = new ArrayList<>();
                        snapSeq = e.seq();
                        inSnap = true;
                    }
                    (e.isBid() ? snapBids : snapAsks).add(new Level(e.price(), e.size()));
                    continue; // never tick mid-snapshot
                }

                if (inSnap) {
                    book.resetTo(snapBids, snapAsks);
                    inSnap = false;
                }
                if (e.isUpdate()) {
                    book.apply(e.isBid(), e.price(), e.size());
                } else if (e.isTrade()) {
                    double v = e.size().doubleValue();
                    double px = e.price().doubleValue();
                    volSinceTick += v;
                    sessionVolume += v;
                    // Queue-position maker fill, gated by PRICE not by the trade's labelled
                    // side. A trade printing at/above our ask reached our ask (consuming ask
                    // liquidity); a print at/below our bid reached our bid. This matches the
                    // live engine and is agnostic to the feed's aggressor-vs-maker "side"
                    // convention — Coinbase documents market_trades "side" as the MAKER side,
                    // the opposite of aggressor, so relying on it would invert the mapping.
                    if (run != null && !halted) {
                        if (qAskPx > 0 && px >= qAskPx && qSzAsk - filledAsk > 1e-12) {
                            cumReachAsk += v;
                            double fill = Math.min(Math.max(0, cumReachAsk - queueAheadAsk), qSzAsk) - filledAsk;
                            if (fill > 1e-9) {
                                run.book().apply(Fill.maker(e.ts(), false, qAskPx, fill));
                                filledAsk += fill;
                            }
                        } else if (qBidPx > 0 && px <= qBidPx && qSzBid - filledBid > 1e-12) {
                            cumReachBid += v;
                            double fill = Math.min(Math.max(0, cumReachBid - queueAheadBid), qSzBid) - filledBid;
                            if (fill > 1e-9) {
                                run.book().apply(Fill.maker(e.ts(), true, qBidPx, fill));
                                filledBid += fill;
                            }
                        }
                    }
                }

                // Advance the strategy on the tick cadence, in virtual (event) time.
                // Once the strategy is done we stop ticking but keep replaying so the final
                // book still marks the resulting position.
                if (!started && book.isReady()) {
                    nextTick = e.ts();
                    started = true;
                }
                while (started && !tradingDone && !e.ts().isBefore(nextTick) && book.isReady()) {
                    double mid = d(book.mid());
                    if (!arrivalSet && mid > 0) {
                        run.setArrivalMid(mid);
                        arrivalSet = true;
                    }
                    MarketState state = new MarketState(product, d(book.bestBid()), d(book.bestAsk()),
                            mid, d(book.microprice()), perTickSigma(mids), volSinceTick);
                    strategy.step(new StrategyContext(state, book, run, e.ts()));
                    // Record the maker's intended quote with a timestamp. The fill model
                    // picks it up `latencyMs` later (see the lag-resolve above) — a fresh
                    // order joins the back of the queue when it actually reaches the market.
                    if (run.quoteSize() > 0) {
                        quoteHist.addLast(new double[]{
                                e.ts().toEpochMilli(), run.quoteBid(), run.quoteAsk(), run.quoteSize()});
                    }
                    run.touch(e.ts());
                    ticks++;
                    if (mid > 0) {
                        mids.addLast(mid);
                        while (mids.size() > VOL_WINDOW) {
                            mids.removeFirst();
                        }
                    }
                    volSinceTick = 0;
                    nextTick = nextTick.plusMillis(tickMs);
                    if (strategy.isDone()) {
                        tradingDone = true;
                    }
                }

                // Resolve markouts now due against the current mid, then schedule markouts
                // for fills created this event (taker fills in the tick, maker fills above).
                double curMid = d(book.mid());
                long nowMs = e.ts().toEpochMilli();
                if (curMid > 0) {
                    // entry = {dueMs, fillPrice, sideSign, fillSize}; weight the markout by size.
                    while (!mk1s.isEmpty() && mk1s.peekFirst()[0] <= nowMs) {
                        double[] m = mk1s.pollFirst();
                        moSum1s += m[3] * m[2] * (curMid - m[1]) / m[1] * 10_000.0;
                        moWt1s += m[3];
                    }
                    while (!mk10s.isEmpty() && mk10s.peekFirst()[0] <= nowMs) {
                        double[] m = mk10s.pollFirst();
                        moSum10s += m[3] * m[2] * (curMid - m[1]) / m[1] * 10_000.0;
                        moWt10s += m[3];
                    }
                }
                List<Fill> soFar = run.book().fills();
                for (int i = lastFillCount; i < soFar.size(); i++) {
                    Fill f = soFar.get(i);
                    double sign = f.isBuy() ? 1 : -1;
                    long ft = f.time().toEpochMilli();
                    mk1s.addLast(new double[]{ft + 1000, f.price(), sign, f.size()});
                    mk10s.addLast(new double[]{ft + 10000, f.price(), sign, f.size()});
                }
                lastFillCount = soFar.size();

                // Kill-switch: track drawdown; on a breach, flatten and stop.
                if (curMid > 0) {
                    double pnlNow = run.book().totalPnl(curMid);
                    peakPnl = Math.max(peakPnl, pnlNow);
                    maxDrawdown = Math.max(maxDrawdown, peakPnl - pnlNow);
                    if (!halted && limits != null) {
                        String breach = null;
                        if (limits.maxDrawdownUsd() != null && peakPnl - pnlNow > limits.maxDrawdownUsd()) {
                            breach = "MAX_DRAWDOWN";
                        } else if (limits.maxLossUsd() != null && pnlNow < -limits.maxLossUsd()) {
                            breach = "MAX_LOSS";
                        } else if (limits.maxPositionSize() != null
                                && Math.abs(run.book().position()) > limits.maxPositionSize()) {
                            breach = "MAX_POSITION";
                        }
                        if (breach != null) {
                            double pos = run.book().position();
                            if (Math.abs(pos) > 1e-9 && book.isReady()) {
                                ExecutionModel.Sweep sw = ExecutionModel.sweep(book, pos < 0, Math.abs(pos));
                                if (sw.filledSize() > 1e-9) {
                                    run.book().apply(Fill.taker(e.ts(), pos < 0, sw.vwap(), sw.filledSize()));
                                }
                            }
                            halted = true;
                            haltReason = breach;
                            tradingDone = true;
                            qSzBid = 0;
                            qSzAsk = 0;
                            log.info("Backtest kill-switch fired: {} — flattened at {}", breach, e.ts());
                        }
                    }
                }
            }
            if (inSnap) {
                book.resetTo(snapBids, snapAsks);
            }
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }

        if (run == null) {
            throw new BadRequestException("No events for product " + product + " in " + file.getFileName());
        }
        double avgMk1s = moWt1s > 1e-12 ? round(moSum1s / moWt1s, 3) : 0;
        double avgMk10s = moWt10s > 1e-12 ? round(moSum10s / moWt10s, 3) : 0;
        return buildResult(req, product, buy, book, run, events, ticks, firstTs, lastTs,
                avgMk1s, avgMk10s, sessionVolume, maxDrawdown, halted, haltReason);
    }

    private BacktestResult buildResult(BacktestRequest req, String product, boolean buy, LiveOrderBook book,
                                       StrategyRun run, long events, long ticks, Instant start, Instant end,
                                       double avgMk1s, double avgMk10s, double sessionVolume,
                                       double maxDrawdown, boolean halted, String haltReason) {
        double execSize = run.executedSize();
        double execNotional = run.executedNotional();
        double avgExec = execSize > 0 ? execNotional / execSize : 0;
        double arrival = run.arrivalMid();
        double isBps = (arrival > 0 && execSize > 0)
                ? (buy ? avgExec - arrival : arrival - avgExec) / arrival * 10_000.0 : 0;

        double finalMark = d(book.mid());
        PnlBook pnl = run.book();
        List<FillView> fills = pnl.fills().stream()
                .map(f -> new FillView(f.time(), f.side(), f.price(), f.size(), f.liquidity()))
                .toList();

        // --- Costs. Takers pay fees + market impact; makers provide liquidity (fee/rebate,
        // no impact). Impact follows the square-root law: cost grows with participation.
        Costs c = req.costs();
        double takerFeeBps = cfg(c == null ? null : c.takerFeeBps(), 5.0);
        double makerFeeBps = cfg(c == null ? null : c.makerFeeBps(), 0.0);
        double commissionBps = cfg(c == null ? null : c.commissionBps(), 0.0);
        double regFeeBps = cfg(c == null ? null : c.regFeeBps(), 0.0);
        double borrowBpsYr = cfg(c == null ? null : c.borrowBpsPerYear(), 0.0);
        double impactCoef = cfg(c == null ? null : c.impactCoef(), 50.0);

        double takerNotional = 0;
        double makerNotional = 0;
        double sellNotional = 0;
        double takerSize = 0;
        for (Fill f : pnl.fills()) {
            double notional = f.price() * f.size();
            if ("MAKER".equals(f.liquidity())) {
                makerNotional += notional;
            } else {
                takerNotional += notional;
                takerSize += f.size();
            }
            if (!f.isBuy()) {
                sellNotional += notional;
            }
        }
        double totalNotional = takerNotional + makerNotional;

        double participation = sessionVolume > 1e-9 ? takerSize / sessionVolume : 0;
        double impactBps = impactCoef * Math.sqrt(participation);
        double impactCost = takerNotional * impactBps / 10_000.0;

        double feeCost = takerNotional * takerFeeBps / 10_000.0
                + makerNotional * makerFeeBps / 10_000.0
                + totalNotional * commissionBps / 10_000.0
                + sellNotional * regFeeBps / 10_000.0;

        double financingCost = 0;
        if (pnl.position() < 0 && finalMark > 0) {
            double years = Math.max(0, (end.toEpochMilli() - start.toEpochMilli()) / 1000.0) / 31_557_600.0;
            financingCost = -pnl.position() * finalMark * borrowBpsYr / 10_000.0 * years;
        }

        double gross = pnl.totalPnl(finalMark);
        double netPnl = gross - feeCost - impactCost - financingCost;
        double feeBps = totalNotional > 0 ? feeCost / totalNotional * 10_000.0 : 0;
        double allInCostBps = totalNotional > 0
                ? (feeCost + impactCost + financingCost) / totalNotional * 10_000.0 : 0;

        int makerFills = (int) pnl.fills().stream().filter(f -> "MAKER".equals(f.liquidity())).count();
        int takerFills = fills.size() - makerFills;

        boolean mm = "AVELLANEDA_STOIKOV".equals(run.type());
        String note = mm
                ? "Two-sided market making: queue-position-aware maker fills, adverse selection in the markouts, and after-cost P&L (makers earn the maker fee/rebate, pay no impact)."
                : (execSize + 1e-9 < (req.size() == null ? 0 : req.size())
                        ? "Partial: the recorded session ended before the schedule completed."
                        : "Taker fills sweep real recorded depth; all-in cost adds fees + square-root market impact on top of that slippage.");
        if (halted) {
            note = "Risk kill-switch fired (" + haltReason + "): position flattened and trading halted. " + note;
        }

        return new BacktestResult(product, run.type(), buy ? "BUY" : "SELL",
                req.size() == null ? 0 : req.size(), execSize, round(avgExec, 8), round(arrival, 8),
                round(isBps, 2), round(finalMark, 8), pnl.position(),
                round(pnl.realized(), 2), round(pnl.unrealized(finalMark), 2), round(gross, 2),
                round(feeCost, 2), round(impactCost, 2), round(financingCost, 2), round(netPnl, 2),
                round(feeBps, 2), round(impactBps, 2), round(allInCostBps, 2),
                round(maxDrawdown, 2), halted, haltReason,
                fills.size(), makerFills, takerFills, avgMk1s, avgMk10s,
                events, ticks, start, end, note, fills);
    }

    /** Sweep a strategy across order sizes to build a capacity curve (cost vs. size). */
    public List<CapacityPoint> capacity(CapacityRequest cap) {
        if (cap.sizes() == null || cap.sizes().isEmpty()) {
            throw new BadRequestException("sizes are required for a capacity sweep");
        }
        List<CapacityPoint> points = new ArrayList<>();
        for (double size : cap.sizes()) {
            BacktestResult r = run(new BacktestRequest(cap.product(), cap.strategyType(), cap.side(), size,
                    cap.slices(), null, null, null, null, null, cap.tickMs(), cap.latencyMs(), cap.date(),
                    cap.costs(), null, null));
            points.add(new CapacityPoint(size, r.executedSize(), r.implementationShortfallBps(),
                    r.feeBps(), r.impactBps(), r.allInCostBps(), r.netPnl()));
        }
        return points;
    }

    /** Replay a strategy across market-condition scenarios — a robustness sweep for overfitting. */
    public List<RobustnessPoint> robustness(RobustnessRequest req) {
        if (req.scenarios() == null || req.scenarios().isEmpty()) {
            throw new BadRequestException("scenarios are required for a robustness sweep");
        }
        List<RobustnessPoint> out = new ArrayList<>();
        for (NamedScenario ns : req.scenarios()) {
            BacktestResult r = run(new BacktestRequest(req.product(), req.strategyType(), req.side(), req.size(),
                    req.slices(), null, null, null, null, req.quoteSize(), req.tickMs(), req.latencyMs(),
                    req.date(), req.costs(), null, ns.scenario()));
            out.add(new RobustnessPoint(ns.label(), r.executedSize(), r.implementationShortfallBps(),
                    r.allInCostBps(), r.netPnl(), r.avgMarkoutBps1s(), r.maxDrawdownUsd(), r.halted()));
        }
        return out;
    }

    private static ScenarioTransform buildTransform(Scenario s) {
        if (s == null) {
            return null;
        }
        return new ScenarioTransform(
                s.volScale() == null ? 1.0 : s.volScale(),
                s.spreadScale() == null ? 1.0 : s.spreadScale(),
                s.liquidityScale() == null ? 1.0 : s.liquidityScale(),
                s.driftBpsPerMin() == null ? 0.0 : s.driftBpsPerMin(),
                s.shockBps() == null ? 0.0 : s.shockBps(),
                s.shockAtSecond() == null ? 0L : s.shockAtSecond());
    }

    private static double cfg(Double v, double def) {
        return v == null ? def : v;
    }

    private Strategy build(BacktestRequest req, boolean buy) {
        double size = req.size() == null ? 1.0 : req.size();
        int slices = req.slices() == null ? 10 : Math.max(1, req.slices());
        String type = req.strategyType() == null ? "TWAP" : req.strategyType().toUpperCase();
        return switch (type) {
            case "TWAP" -> new TwapExecution(buy, size, slices);
            case "POV" -> new PovExecution(buy, size, slices, req.participation() == null ? 0.1 : req.participation());
            case "ALMGREN_CHRISS" ->
                    new AlmgrenChrissExecution(buy, size, slices, req.kappa() == null ? 0.3 : req.kappa());
            case "AVELLANEDA_STOIKOV" -> new AvellanedaStoikovMaker(
                    req.gamma() == null ? 0.3 : req.gamma(),
                    req.kappa() == null ? 1.5 : req.kappa(),
                    req.tau() == null ? 60.0 : req.tau(),
                    req.quoteSize() == null ? (req.size() == null ? 0.05 : req.size()) : req.quoteSize());
            default -> throw new BadRequestException("Unknown strategyType: " + type);
        };
    }

    private Path resolveFile(String date) {
        Path dir = Path.of(props.getL2CaptureDir());
        if (date != null && !date.isBlank()) {
            Path f = dir.resolve("l2-" + date + ".csv");
            if (!Files.exists(f)) {
                throw new NotFoundException("No capture file for " + date + " at " + f);
            }
            return f;
        }
        if (!Files.isDirectory(dir)) {
            throw new NotFoundException("No L2 capture directory at " + dir.toAbsolutePath()
                    + " — run the backend with the crypto feed to record L2 first");
        }
        try (Stream<Path> files = Files.list(dir)) {
            return files.filter(p -> p.getFileName().toString().matches("l2-.*\\.csv"))
                    .max((a, b) -> a.getFileName().toString().compareTo(b.getFileName().toString()))
                    .orElseThrow(() -> new NotFoundException("No L2 capture files in " + dir.toAbsolutePath()));
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    private static L2Event parse(String line) {
        try {
            String[] f = line.split(",", 7);
            if (f.length < 7) {
                return null;
            }
            return new L2Event(Long.parseLong(f[0]), Instant.parse(f[1]), f[2], f[3], f[4],
                    new BigDecimal(f[5]), new BigDecimal(f[6]));
        } catch (RuntimeException ex) {
            return null; // skip malformed lines
        }
    }

    private static double perTickSigma(Deque<Double> mids) {
        if (mids.size() < 2) {
            return 0;
        }
        Double[] a = mids.toArray(new Double[0]);
        double mean = 0;
        double[] rets = new double[a.length - 1];
        for (int i = 1; i < a.length; i++) {
            rets[i - 1] = Math.log(a[i] / a[i - 1]);
            mean += rets[i - 1];
        }
        mean /= rets.length;
        double var = 0;
        for (double r : rets) {
            var += (r - mean) * (r - mean);
        }
        return Math.sqrt(var / rets.length);
    }

    private static double d(BigDecimal v) {
        return v == null ? 0 : v.doubleValue();
    }

    private static double round(double v, int dp) {
        double scale = Math.pow(10, dp);
        return Math.round(v * scale) / scale;
    }
}
