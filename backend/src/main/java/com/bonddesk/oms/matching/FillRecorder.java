package com.bonddesk.oms.matching;

import com.bonddesk.oms.service.OrderService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * Records engine {@link DeskFillEvent}s against OMS orders. Listening (rather than being
 * called directly by the engine) keeps the dependency arrow pointing one way: the engine
 * knows nothing about the order service.
 */
@Component
public class FillRecorder {

    private static final Logger log = LoggerFactory.getLogger(FillRecorder.class);

    private final OrderService orders;

    public FillRecorder(OrderService orders) {
        this.orders = orders;
    }

    @EventListener
    public void onDeskFill(DeskFillEvent e) {
        try {
            orders.recordFill(e.orderRef(), e.quantity(), e.price(), e.venue());
        } catch (RuntimeException ex) {
            // The order may have been cancelled or completed between match and record.
            log.debug("Skipped fill for {}: {}", e.orderRef(), ex.getMessage());
        }
    }
}
