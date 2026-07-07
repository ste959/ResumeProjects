package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.equities.AlpacaBrokerClient;
import com.bonddesk.oms.equities.AlpacaBrokerClient.MarketClock;
import com.bonddesk.oms.equities.AlpacaMarketDataClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Market-hours auto-rebalancer: once per trading day, while the exchange is open, snaps positions
 * to the broker and routes the target-book delta orders sized against live marks.
 *
 * <p>Layered SAFETY: it does nothing unless {@code oms.rebalance.auto-enabled} is on AND the module
 * is enabled; nothing when the broker reports the market closed (an unreachable broker reads as
 * closed); and at most once per calendar day in America/New_York. The whole body is wrapped so a
 * throw can never cancel the recurring @Scheduled task. Sizing/routing still passes through the
 * unchanged risk-capped, paper-only {@link RebalanceService}.
 */
@Component
public class RebalanceScheduler {

    private static final Logger log = LoggerFactory.getLogger(RebalanceScheduler.class);

    /** Trading calendar is anchored to the US equity session, regardless of server timezone. */
    private static final ZoneId EXCHANGE_ZONE = ZoneId.of("America/New_York");

    private final RebalanceProperties props;
    private final AlpacaBrokerClient broker;
    private final AlpacaMarketDataClient marketData;
    private final TargetBookLoader targetBookLoader;
    private final RebalanceService rebalanceService;
    private final PositionReconciler reconciler;
    private final RebalanceState state;
    private final Clock clock;

    public RebalanceScheduler(RebalanceProperties props, AlpacaBrokerClient broker,
                              AlpacaMarketDataClient marketData, TargetBookLoader targetBookLoader,
                              RebalanceService rebalanceService, PositionReconciler reconciler,
                              RebalanceState state, Clock clock) {
        this.props = props;
        this.broker = broker;
        this.marketData = marketData;
        this.targetBookLoader = targetBookLoader;
        this.rebalanceService = rebalanceService;
        this.reconciler = reconciler;
        this.state = state;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${oms.rebalance.check-interval-ms:300000}")
    public void tick() {
        try {
            if (!props.isAutoEnabled()) {
                return;
            }
            MarketClock c = broker.clock();
            if (c == null || !c.open()) {
                return;
            }
            LocalDate today = LocalDate.ofInstant(clock.instant(), EXCHANGE_ZONE);
            if (today.equals(state.lastRunDate())) {
                return; // already ran once this trading day
            }

            reconciler.reconcile();

            BigDecimal capital = props.getGrossCapital();
            String portfolio = props.getPortfolio();
            Map<String, BigDecimal> marks = marketData.latestPrices(bookSymbols());
            RebalanceResult result = rebalanceService.execute(capital, portfolio, false, marks);
            state.record(clock.instant(), today, result);
            log.info("Auto-rebalance for {} on {}: {} ({} routed, {} skipped, {} rejected)",
                    portfolio, today, result.status(), result.routed(), result.skipped(), result.rejected());
        } catch (Exception e) {
            // A scheduler throw must not cancel the recurring task.
            log.warn("Auto-rebalance tick failed: {}", e.toString());
        }
    }

    /** Target-book symbols to fetch live marks for; empty if the book is missing/unreadable. */
    private List<String> bookSymbols() {
        try {
            TargetBook book = targetBookLoader.load();
            List<String> out = new ArrayList<>();
            if (book.names() != null) {
                for (TargetWeight name : book.names()) {
                    if (name.symbol() != null && !name.symbol().isBlank()) {
                        out.add(name.symbol());
                    }
                }
            }
            return out;
        } catch (RuntimeException e) {
            log.debug("Could not read target-book symbols for live pricing: {}", e.getMessage());
            return List.of();
        }
    }
}
