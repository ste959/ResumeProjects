package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.equities.AlpacaBrokerClient;
import com.bonddesk.oms.equities.AlpacaMarketDataClient;
import com.bonddesk.oms.equities.AlpacaBrokerClient.MarketClock;
import com.bonddesk.oms.repository.PositionRepository;
import com.bonddesk.oms.risk.RiskLimitProperties;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Read-only operational status for the equity paper-trading loop: broker reachability, market
 * hours, the loaded target book, current portfolio exposure, the binding risk caps, and the last
 * auto-rebalance run. Deliberately UNGATED (unlike the rebalance action endpoint) so ops can always
 * see the loop's state, and every external call is guarded so an unreachable Alpaca never 500s it.
 */
@RestController
@RequestMapping("/api/equity")
@Tag(name = "Equity Ops", description = "Read-only status for the equity paper-trading loop")
public class EquityOpsController {

    private static final Logger log = LoggerFactory.getLogger(EquityOpsController.class);

    private final AlpacaBrokerClient broker;
    private final AlpacaMarketDataClient marketData;
    private final RebalanceProperties rebalanceProps;
    private final RiskLimitProperties riskLimits;
    private final TargetBookLoader targetBookLoader;
    private final PositionRepository positions;
    private final RebalanceState state;

    public EquityOpsController(AlpacaBrokerClient broker, AlpacaMarketDataClient marketData,
                               RebalanceProperties rebalanceProps, RiskLimitProperties riskLimits,
                               TargetBookLoader targetBookLoader, PositionRepository positions,
                               RebalanceState state) {
        this.broker = broker;
        this.marketData = marketData;
        this.rebalanceProps = rebalanceProps;
        this.riskLimits = riskLimits;
        this.targetBookLoader = targetBookLoader;
        this.positions = positions;
        this.state = state;
    }

    @GetMapping("/status")
    @Operation(summary = "Operational status of the equity paper-trading loop (read-only, never routes)")
    public Map<String, Object> status() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("brokerReachable", broker.brokerReachable());
        out.put("marketOpen", marketOpen());
        out.put("autoEnabled", rebalanceProps.isAutoEnabled());
        out.put("targetBook", targetBookSummary());
        out.put("positions", positionSummary());
        out.put("riskCaps", riskCaps());
        out.put("lastRebalance", lastRebalance());
        return out;
    }

    /** Broker market clock, guarded so an unreachable broker reads as closed rather than 500ing. */
    private boolean marketOpen() {
        try {
            MarketClock c = broker.clock();
            return c != null && c.open();
        } catch (RuntimeException e) {
            log.debug("Market clock unavailable for status: {}", e.getMessage());
            return false;
        }
    }

    /** {asOf, names} for the loaded target book; null when the book is missing/unreadable. */
    private Map<String, Object> targetBookSummary() {
        try {
            TargetBook book = targetBookLoader.load();
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("asOf", book.asOf());
            m.put("names", book.names() == null ? 0 : book.names().size());
            return m;
        } catch (RuntimeException e) {
            log.debug("Target book unavailable for status: {}", e.getMessage());
            return null;
        }
    }

    /** Count and long/short/net exposure for the rebalance portfolio, marked at LIVE prices where
     * available (falling back to each security's cleanPrice), so the status shows real MTM. */
    private Map<String, Object> positionSummary() {
        Map<String, Object> m = new LinkedHashMap<>();
        int count = 0;
        BigDecimal grossLong = BigDecimal.ZERO;
        BigDecimal grossShort = BigDecimal.ZERO;
        try {
            List<Position> held = positions.findByPortfolioOrderBySecurity_Cusip(rebalanceProps.getPortfolio());
            // One batched snapshot call for live marks; empty (and harmless) if Alpaca is unreachable.
            Map<String, BigDecimal> live = Map.of();
            try {
                List<String> tickers = held.stream().map(Position::getSecurity)
                        .filter(s -> s != null && s.getTicker() != null).map(Security::getTicker).toList();
                if (!tickers.isEmpty()) {
                    live = marketData.latestPrices(tickers);
                }
            } catch (RuntimeException e) {
                log.debug("Live marks unavailable for status: {}", e.getMessage());
            }
            for (Position p : held) {
                count++;
                Security sec = p.getSecurity();
                BigDecimal qty = p.getNetQuantity();
                BigDecimal price = sec == null ? null : live.getOrDefault(sec.getTicker(), sec.getCleanPrice());
                if (qty == null || price == null) {
                    continue;
                }
                BigDecimal notional = qty.multiply(price);
                if (qty.signum() > 0) {
                    grossLong = grossLong.add(notional);
                } else if (qty.signum() < 0) {
                    grossShort = grossShort.add(notional);
                }
            }
        } catch (RuntimeException e) {
            log.debug("Position exposure unavailable for status: {}", e.getMessage());
        }
        m.put("count", count);
        m.put("grossLong", grossLong);
        m.put("grossShort", grossShort);
        m.put("net", grossLong.add(grossShort));
        return m;
    }

    private Map<String, Object> riskCaps() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("desk", riskLimits.getMaxGrossNotional());
        m.put("rebalanceBook", rebalanceProps.getMaxGrossNotional());
        return m;
    }

    private Map<String, Object> lastRebalance() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("time", state.lastRunTime());
        m.put("status", state.status());
        m.put("routed", state.routed());
        m.put("skipped", state.skipped());
        m.put("rejected", state.rejected());
        return m;
    }
}
