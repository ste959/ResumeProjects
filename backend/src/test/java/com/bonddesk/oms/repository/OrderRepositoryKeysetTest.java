package com.bonddesk.oms.repository;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.domain.TimeInForce;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.PageRequest;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The keyset blotter query against a real database (embedded H2, no Docker): newest-first ordering, a
 * cursor that pages without overlap or gaps, a stable tie-break when timestamps collide, and the
 * status filter. This is the correctness-critical half of pagination — the {@code (createdAt, id)}
 * keyset predicate — verified end-to-end on SQL.
 */
@DataJpaTest
class OrderRepositoryKeysetTest {

    @Autowired
    private OrderRepository orders;

    @Autowired
    private SecurityRepository securities;

    private static final Instant BASE = Instant.parse("2026-01-01T00:00:00Z");

    @Test
    void pagesNewestFirstThroughACursorWithoutGapsOrOverlaps() {
        Security sec = persistSecurity("111111111");
        // 7 orders, createdAt increasing with i — so order 6 is newest.
        for (int i = 0; i < 7; i++) {
            persistOrder(sec, "ref-" + i, OrderStatus.NEW, BASE.plusSeconds(i));
        }

        List<String> pagedRefs = new ArrayList<>();
        Instant cursorTs = null;
        Long cursorId = null;
        for (int guard = 0; guard < 10; guard++) {
            List<Order> page = orders.findBlotterPage(null, null, cursorTs, cursorId, PageRequest.of(0, 3));
            if (page.isEmpty()) {
                break;
            }
            page.forEach(o -> pagedRefs.add(o.getOrderRef()));
            Order last = page.get(page.size() - 1);
            cursorTs = last.getCreatedAt();
            cursorId = last.getId();
        }

        // Every order seen exactly once, strictly newest-first.
        assertThat(pagedRefs).containsExactly("ref-6", "ref-5", "ref-4", "ref-3", "ref-2", "ref-1", "ref-0");
    }

    @Test
    void breaksTimestampTiesByIdSoPagingStaysStable() {
        Security sec = persistSecurity("222222222");
        // Three orders share the exact same createdAt — only the id can order them.
        Order a = persistOrder(sec, "tie-a", OrderStatus.NEW, BASE);
        Order b = persistOrder(sec, "tie-b", OrderStatus.NEW, BASE);
        Order c = persistOrder(sec, "tie-c", OrderStatus.NEW, BASE);

        List<Order> firstTwo = orders.findBlotterPage(null, null, null, null, PageRequest.of(0, 2));
        assertThat(firstTwo).extracting(Order::getId).containsExactly(c.getId(), b.getId());

        // Continue from the second row — the keyset must resume at the third, not repeat b.
        Order last = firstTwo.get(1);
        List<Order> next = orders.findBlotterPage(null, null, last.getCreatedAt(), last.getId(), PageRequest.of(0, 2));
        assertThat(next).extracting(Order::getId).containsExactly(a.getId());
    }

    @Test
    void filtersByStatus() {
        Security sec = persistSecurity("333333333");
        persistOrder(sec, "new-1", OrderStatus.NEW, BASE.plusSeconds(1));
        persistOrder(sec, "filled-1", OrderStatus.FILLED, BASE.plusSeconds(2));
        persistOrder(sec, "new-2", OrderStatus.NEW, BASE.plusSeconds(3));

        List<Order> filled = orders.findBlotterPage(OrderStatus.FILLED, null, null, null, PageRequest.of(0, 10));
        assertThat(filled).extracting(Order::getOrderRef).containsExactly("filled-1");
    }

    private Security persistSecurity(String cusip) {
        Security s = new Security();
        s.setCusip(cusip);
        s.setAssetClass(AssetClass.FIXED_INCOME);
        s.setDescription("US TREASURY 1.5% 2030");
        s.setIssuer("US TREASURY");
        s.setCurrency("USD");
        s.setSector("SOVEREIGN");
        s.setCleanPrice(new BigDecimal("99.5000"));
        return securities.save(s);
    }

    private Order persistOrder(Security sec, String ref, OrderStatus status, Instant createdAt) {
        Order o = new Order();
        o.setOrderRef(ref);
        o.setSecurity(sec);
        o.setPortfolio("PORT-DEMO");
        o.setTrader("trader1");
        o.setSide(OrderSide.BUY);
        o.setOrderType(OrderType.MARKET);
        o.setTimeInForce(TimeInForce.DAY);
        o.setQuantity(new BigDecimal("1000000"));
        o.setStatus(status);
        o.setCreatedAt(createdAt);
        o.setUpdatedAt(createdAt);
        return orders.save(o);
    }
}
