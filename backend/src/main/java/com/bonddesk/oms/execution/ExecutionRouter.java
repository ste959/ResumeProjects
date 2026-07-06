package com.bonddesk.oms.execution;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.equities.AlpacaExecutionVenue;
import com.bonddesk.oms.matching.MatchingGateway;
import com.bonddesk.oms.matching.MatchingService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.util.Optional;

/**
 * Routes a routed order to the execution venue for its asset class, so one order lifecycle
 * spans multiple markets:
 * <ul>
 *   <li><b>Equities</b> → the Alpaca (paper) broker.</li>
 *   <li><b>Fixed income</b> → the in-process CLOB matching engine (when enabled), else it
 *       stays working for manual/RFQ fills.</li>
 * </ul>
 *
 * <p>This is the single {@link MatchingGateway} that {@code OrderService} sees (marked
 * {@link Primary}); the underlying venues are injected by concrete type so there is no
 * self-referential ambiguity. Both are optional — absent venues degrade to a no-op.
 */
@Component
@Primary
public class ExecutionRouter implements MatchingGateway {

    private static final Logger log = LoggerFactory.getLogger(ExecutionRouter.class);

    private final Optional<MatchingService> clob;
    private final Optional<AlpacaExecutionVenue> equities;

    public ExecutionRouter(Optional<MatchingService> clob, Optional<AlpacaExecutionVenue> equities) {
        this.clob = clob;
        this.equities = equities;
    }

    @Override
    public void route(Order order) {
        AssetClass assetClass = order.getSecurity().getAssetClass();
        if (assetClass == AssetClass.EQUITY) {
            equities.ifPresentOrElse(v -> v.route(order),
                    () -> log.warn("No equity venue for order {} — equities module disabled", order.getOrderRef()));
        } else {
            clob.ifPresent(v -> v.route(order));
        }
    }

    @Override
    public void cancel(Order order) {
        AssetClass assetClass = order.getSecurity().getAssetClass();
        if (assetClass == AssetClass.EQUITY) {
            equities.ifPresent(v -> v.cancel(order));
        } else {
            clob.ifPresent(v -> v.cancel(order));
        }
    }
}
