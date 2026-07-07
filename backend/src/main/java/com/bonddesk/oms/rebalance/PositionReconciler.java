package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.equities.AlpacaBrokerClient;
import com.bonddesk.oms.equities.AlpacaBrokerClient.BrokerPosition;
import com.bonddesk.oms.repository.SecurityRepository;
import com.bonddesk.oms.service.PositionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

/**
 * Snaps the OMS equity position book to the broker's truth: the standard reconciliation an OMS
 * needs when an external venue — not the in-process matching engine — is the system of record for
 * fills. For each broker position it overwrites the OMS position (absolute quantity + avg entry
 * price); any OMS equity position the broker no longer holds is flattened to zero.
 *
 * <p>Read-mostly and defensive: with no credentials it no-ops, and an unknown broker symbol is
 * skipped rather than fabricated, so a partial security master can never corrupt the book.
 */
@Component
public class PositionReconciler {

    private static final Logger log = LoggerFactory.getLogger(PositionReconciler.class);

    private final AlpacaBrokerClient broker;
    private final SecurityRepository securities;
    private final PositionService positions;
    private final RebalanceProperties props;

    public PositionReconciler(AlpacaBrokerClient broker, SecurityRepository securities,
                              PositionService positions, RebalanceProperties props) {
        this.broker = broker;
        this.securities = securities;
        this.positions = positions;
        this.props = props;
    }

    /** Reconcile once on startup, but only when explicitly opted in via oms.rebalance.reconcile-positions. */
    @EventListener(ApplicationReadyEvent.class)
    void reconcileOnStartup() {
        if (!props.isReconcilePositions()) {
            return;
        }
        try {
            ReconcileSummary summary = reconcile();
            log.info("Startup position reconcile: {} updated, {} flattened, {} unknown",
                    summary.updated(), summary.flattened(), summary.unknown());
        } catch (RuntimeException e) {
            log.warn("Startup position reconcile failed: {}", e.getMessage());
        }
    }

    /**
     * Pull the broker's open positions and snap the OMS book to them, flattening any stale OMS
     * equity position the broker no longer holds. No-op (empty summary) without credentials.
     */
    public ReconcileSummary reconcile() {
        if (!broker.brokerReachable()) {
            log.debug("Position reconcile skipped — no Alpaca credentials");
            return ReconcileSummary.empty();
        }
        String portfolio = props.getPortfolio();

        Map<String, BrokerPosition> byTicker = new HashMap<>();
        for (BrokerPosition bp : broker.positions()) {
            if (bp.symbol() != null) {
                byTicker.put(bp.symbol(), bp);
            }
        }

        int updated = 0;
        int unknown = 0;
        for (BrokerPosition bp : byTicker.values()) {
            Security sec = securities.findByTicker(bp.symbol()).orElse(null);
            if (sec == null) {
                log.debug("Broker position {} has no matching security in the OMS master — skipped", bp.symbol());
                unknown++;
                continue;
            }
            BigDecimal qty = bp.qty() == null ? BigDecimal.ZERO : bp.qty();
            BigDecimal avg = bp.avgEntryPrice() == null ? BigDecimal.ZERO : bp.avgEntryPrice();
            positions.setPosition(portfolio, sec, qty, avg);
            updated++;
        }

        int flattened = 0;
        for (Position p : positions.forPortfolio(portfolio)) {
            Security sec = p.getSecurity();
            if (sec == null || sec.getAssetClass() != AssetClass.EQUITY || sec.getTicker() == null) {
                continue;
            }
            BigDecimal net = p.getNetQuantity();
            boolean nonZero = net != null && net.signum() != 0;
            if (nonZero && !byTicker.containsKey(sec.getTicker())) {
                positions.setPosition(portfolio, sec, BigDecimal.ZERO, BigDecimal.ZERO);
                flattened++;
            }
        }

        return new ReconcileSummary(updated, flattened, unknown);
    }
}
