package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.domain.TimeInForce;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.bonddesk.oms.equities.AlpacaBrokerClient;
import com.bonddesk.oms.repository.SecurityRepository;
import com.bonddesk.oms.risk.RiskLimitProperties;
import com.bonddesk.oms.service.OrderService;
import com.bonddesk.oms.service.PositionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Turns a research target book into delta orders and routes them to the (paper) execution
 * venue. This validates the whole signal → order → fill → reconcile chain end to end; it is
 * <em>not</em> alpha deployment (the research found no edge), so it is built defensively:
 * every name is guarded so one bad symbol cannot abort the batch, an aggregate gross-notional
 * risk cap blocks the whole run, and the default entry point is a side-effect-free dry run.
 */
@Service
public class RebalanceService {

    private static final Logger log = LoggerFactory.getLogger(RebalanceService.class);

    /** Bot identity recorded as the trader on rebalance-generated orders. */
    private static final String REBAL_TRADER = "REBAL-BOT";

    private final TargetBookLoader targetBookLoader;
    private final PositionService positions;
    private final OrderService orders;
    private final SecurityRepository securities;
    private final AlpacaBrokerClient broker;
    private final RiskLimitProperties riskLimits;
    private final RebalanceProperties rebalanceProps;

    public RebalanceService(TargetBookLoader targetBookLoader, PositionService positions,
                            OrderService orders, SecurityRepository securities,
                            AlpacaBrokerClient broker, RiskLimitProperties riskLimits,
                            RebalanceProperties rebalanceProps) {
        this.targetBookLoader = targetBookLoader;
        this.positions = positions;
        this.orders = orders;
        this.securities = securities;
        this.broker = broker;
        this.riskLimits = riskLimits;
        this.rebalanceProps = rebalanceProps;
    }

    /** The binding gross-notional cap for a rebalance: the TIGHTER of the desk-wide risk limit and
     * the rebalance-specific limit. Keeps the paper equity book on a short leash ($250k default)
     * without lowering the desk-wide cap below the bond side's per-order compliance ($25MM). */
    private BigDecimal effectiveGrossCap() {
        BigDecimal desk = riskLimits.getMaxGrossNotional();
        BigDecimal book = rebalanceProps.getMaxGrossNotional();
        if (desk == null || desk.signum() <= 0) {
            return book;
        }
        if (book == null || book.signum() <= 0) {
            return desk;
        }
        return desk.min(book);
    }

    /**
     * Compute the delta orders needed to move {@code portfolio} to the target book scaled to
     * {@code grossCapital}. Pure arithmetic — no orders are created and nothing is persisted.
     */
    public RebalancePlan plan(BigDecimal grossCapital, String portfolio) {
        return buildPlan(targetBookLoader.load(), grossCapital, portfolio, Map.of());
    }

    /**
     * The effective sizing price for a name: a live override when present and positive, otherwise
     * the target-book reference price. Overrides let the scheduler size against current marks.
     */
    private BigDecimal priceFor(TargetWeight name, Map<String, BigDecimal> priceOverrides) {
        BigDecimal override = priceOverrides == null ? null : priceOverrides.get(name.symbol());
        if (override != null && override.signum() > 0) {
            return override;
        }
        return name.price();
    }

    private RebalancePlan buildPlan(TargetBook book, BigDecimal grossCapital, String portfolio,
                                    Map<String, BigDecimal> priceOverrides) {
        Map<String, BigDecimal> currentByTicker = currentSharesByTicker(portfolio);

        List<PlannedTrade> trades = new ArrayList<>();
        BigDecimal projectedGross = BigDecimal.ZERO;

        for (TargetWeight name : book.names()) {
            BigDecimal price = priceFor(name, priceOverrides);
            if (name.symbol() == null || price == null || name.weight() == null
                    || price.signum() <= 0) {
                log.debug("Skipping malformed target name: {}", name);
                continue;
            }

            // targetShares = round-half-up(weight * grossCapital / price) as whole shares (signed).
            BigDecimal targetShares = name.weight().multiply(grossCapital)
                    .divide(price, 0, RoundingMode.HALF_UP);

            projectedGross = projectedGross.add(targetShares.multiply(price).abs());

            BigDecimal currentShares = currentByTicker.getOrDefault(name.symbol(), BigDecimal.ZERO);
            BigDecimal delta = targetShares.subtract(currentShares);
            if (delta.abs().compareTo(BigDecimal.ONE) < 0) {
                continue; // sub-one-share delta — not worth a ticket
            }

            OrderSide side = delta.signum() > 0 ? OrderSide.BUY : OrderSide.SELL;
            boolean shortSale = targetShares.signum() < 0
                    || (delta.signum() < 0 && currentShares.signum() <= 0);
            trades.add(new PlannedTrade(name.symbol(), name.symbol(), side, delta.abs(),
                    price, targetShares, currentShares, shortSale));
        }

        BigDecimal max = effectiveGrossCap();
        boolean withinRiskLimit = max == null || max.signum() <= 0 || projectedGross.compareTo(max) <= 0;

        return new RebalancePlan(portfolio, grossCapital, book.asOf(), trades, projectedGross, withinRiskLimit);
    }

    /**
     * Build the plan and, unless it is a dry run or blocked by risk, route each delta order to
     * the venue through the standard create → stage → route lifecycle.
     */
    public RebalanceResult execute(BigDecimal grossCapital, String portfolio, boolean dryRun) {
        return execute(grossCapital, portfolio, dryRun, Map.of());
    }

    /**
     * As {@link #execute(BigDecimal, String, boolean)}, but a live price override (symbol -> mark)
     * replaces the target-book price for sizing AND the {@code Security.cleanPrice} refresh. An
     * empty map reproduces the pure target-book path exactly.
     */
    public RebalanceResult execute(BigDecimal grossCapital, String portfolio, boolean dryRun,
                                   Map<String, BigDecimal> priceOverrides) {
        TargetBook book = targetBookLoader.load();
        RebalancePlan plan = buildPlan(book, grossCapital, portfolio, priceOverrides);

        if (!plan.withinRiskLimit()) {
            log.warn("Rebalance for {} BLOCKED: projected gross notional {} exceeds the cap {}",
                    portfolio, plan.projectedGrossNotional(), effectiveGrossCap());
            return RebalanceResult.planOnly(plan, "BLOCKED_RISK_LIMIT");
        }

        if (dryRun) {
            log.info("Rebalance DRY_RUN for {}: {} delta trades, projected gross {}",
                    portfolio, plan.trades().size(), plan.projectedGrossNotional());
            return RebalanceResult.planOnly(plan, "DRY_RUN");
        }

        // Live path: refresh each named security's reference price (live override when present,
        // else the target-book price) so the downstream pre-trade risk guard and position marks
        // size against current prices.
        refreshPrices(book, priceOverrides);

        boolean reachable = broker.brokerReachable();
        List<TradeOutcome> outcomes = new ArrayList<>();
        for (PlannedTrade trade : plan.trades()) {
            outcomes.add(routeOne(trade, portfolio, reachable));
        }

        RebalanceResult result = RebalanceResult.of(plan, "ROUTED", outcomes);
        log.info("Rebalance for {} ROUTED: {} routed, {} skipped, {} rejected of {} deltas",
                portfolio, result.routed(), result.skipped(), result.rejected(), plan.trades().size());
        return result;
    }

    /** Route a single delta order, guarding create/stage/route so one bad name cannot abort the batch. */
    private TradeOutcome routeOne(PlannedTrade trade, String portfolio, boolean reachable) {
        if (trade.shortSale() && reachable && !broker.isShortable(trade.symbol())) {
            log.info("Skipping short {} — not shortable at venue", trade.symbol());
            return TradeOutcome.skipped(trade, "not shortable");
        }
        try {
            CreateOrderRequest req = new CreateOrderRequest(trade.cusip(), portfolio, REBAL_TRADER,
                    trade.side(), OrderType.MARKET, TimeInForce.DAY, trade.qty(), null);
            Order created = orders.create(req);
            orders.stage(created.getOrderRef());
            orders.route(created.getOrderRef());
            return TradeOutcome.routed(trade, created.getOrderRef());
        } catch (RuntimeException e) {
            log.warn("Rebalance trade for {} rejected: {}", trade.symbol(), e.getMessage());
            return TradeOutcome.rejected(trade, e.getMessage());
        }
    }

    /** Signed net shares per equity ticker for the portfolio (bonds and null tickers ignored). */
    private Map<String, BigDecimal> currentSharesByTicker(String portfolio) {
        Map<String, BigDecimal> byTicker = new HashMap<>();
        for (Position p : positions.forPortfolio(portfolio)) {
            Security sec = p.getSecurity();
            if (sec == null || sec.getTicker() == null) {
                continue;
            }
            byTicker.put(sec.getTicker(), p.getNetQuantity() == null ? BigDecimal.ZERO : p.getNetQuantity());
        }
        return byTicker;
    }

    /** Overwrite each named security's reference price with its effective mark (live override when
     * present, else the target-book price). Guarded per name. */
    private void refreshPrices(TargetBook book, Map<String, BigDecimal> priceOverrides) {
        for (TargetWeight name : book.names()) {
            BigDecimal price = priceFor(name, priceOverrides);
            if (name.symbol() == null || price == null || price.signum() <= 0) {
                continue;
            }
            try {
                securities.findByTicker(name.symbol()).ifPresent(sec -> {
                    sec.setCleanPrice(price);
                    securities.save(sec);
                });
            } catch (RuntimeException e) {
                log.debug("Could not refresh price for {}: {}", name.symbol(), e.getMessage());
            }
        }
    }
}
