package com.bonddesk.oms.matching;

import com.bonddesk.oms.exception.InvalidStateTransitionException;
import com.bonddesk.oms.service.OrderService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Component;

/**
 * Records engine {@link DeskFillEvent}s against OMS orders. Listening (rather than being
 * called directly by the engine) keeps the dependency arrow pointing one way: the engine
 * knows nothing about the order service.
 *
 * <p>A recorded fill is real economic state, so failures are handled by cause rather than swallowed:
 * an already-cancelled/completed order is the one genuinely-expected race (logged at debug); an
 * optimistic-lock conflict with a concurrent write is retried; anything else is logged at ERROR — a
 * dropped fill must never be invisible.
 */
@Component
public class FillRecorder {

    private static final Logger log = LoggerFactory.getLogger(FillRecorder.class);
    private static final int MAX_ATTEMPTS = 3;

    private final OrderService orders;

    public FillRecorder(OrderService orders) {
        this.orders = orders;
    }

    @EventListener
    public void onDeskFill(DeskFillEvent e) {
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            try {
                orders.recordFill(e.orderRef(), e.quantity(), e.price(), e.venue());
                return;
            } catch (InvalidStateTransitionException ex) {
                // Expected race: the order was cancelled/completed between match and record — not a loss.
                log.debug("Skipped fill for {}: {}", e.orderRef(), ex.getMessage());
                return;
            } catch (OptimisticLockingFailureException ex) {
                // A concurrent write (e.g. a REST cancel) won the @Version race; reload and retry.
                if (attempt == MAX_ATTEMPTS) {
                    log.error("Fill for {} LOST after {} optimistic-lock retries — qty={} @ {}",
                            e.orderRef(), MAX_ATTEMPTS, e.quantity(), e.price(), ex);
                    return;
                }
            } catch (RuntimeException ex) {
                // Unexpected: never silently drop a fill — surface it loudly for reconciliation.
                log.error("Fill for {} FAILED and was dropped — qty={} @ {}",
                        e.orderRef(), e.quantity(), e.price(), ex);
                return;
            }
        }
    }
}
