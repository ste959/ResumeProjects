package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.repository.PositionRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * Verifies the weighted-average-cost bookkeeping without a database, using a
 * one-slot in-memory stand-in for the repository.
 */
class PositionServiceTest {

    private PositionService service;
    private Security bond;

    @BeforeEach
    void setUp() {
        PositionRepository repo = mock(PositionRepository.class);
        AtomicReference<Position> stored = new AtomicReference<>();
        when(repo.findByPortfolioAndSecurity_Cusip(any(), any()))
                .thenAnswer(i -> Optional.ofNullable(stored.get()));
        when(repo.save(any(Position.class))).thenAnswer(i -> {
            Position p = i.getArgument(0);
            stored.set(p);
            return p;
        });

        Clock clock = Clock.fixed(Instant.parse("2026-07-02T00:00:00Z"), ZoneOffset.UTC);
        service = new PositionService(repo, clock);

        bond = new Security();
        bond.setCusip("912828YK0");
    }

    private Position fill(OrderSide side, String qty, String price) {
        return service.applyFill("PORT-A", bond, side, new BigDecimal(qty), new BigDecimal(price));
    }

    @Test
    void buyingOpensAndBlendsCost() {
        fill(OrderSide.BUY, "1000000", "99.0000");
        Position p = fill(OrderSide.BUY, "1000000", "101.0000");

        assertThat(p.getNetQuantity()).isEqualByComparingTo("2000000");
        assertThat(p.getAvgCost()).isEqualByComparingTo("100.0000");
    }

    @Test
    void reducingKeepsAverageCost() {
        fill(OrderSide.BUY, "1000000", "99.0000");
        fill(OrderSide.BUY, "1000000", "101.0000"); // avg 100
        Position p = fill(OrderSide.SELL, "500000", "105.0000");

        assertThat(p.getNetQuantity()).isEqualByComparingTo("1500000");
        assertThat(p.getAvgCost()).isEqualByComparingTo("100.0000");
    }

    @Test
    void closingToFlatResetsCost() {
        fill(OrderSide.BUY, "1000000", "99.0000");
        Position p = fill(OrderSide.SELL, "1000000", "105.0000");

        assertThat(p.getNetQuantity()).isEqualByComparingTo("0");
        assertThat(p.getAvgCost()).isEqualByComparingTo("0");
    }

    @Test
    void flippingThroughZeroRepricesResidualAtTradePrice() {
        fill(OrderSide.BUY, "1000000", "99.0000");
        Position p = fill(OrderSide.SELL, "1500000", "98.0000");

        assertThat(p.getNetQuantity()).isEqualByComparingTo("-500000");
        assertThat(p.getAvgCost()).isEqualByComparingTo("98.0000");
    }
}
