package com.bonddesk.oms.risk;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.service.PositionService;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class PreTradeRiskGuardTest {

    private final PositionService positions = mock(PositionService.class);
    private final RiskLimitProperties limits = new RiskLimitProperties();
    private final PreTradeRiskGuard guard = new PreTradeRiskGuard(positions, limits);

    private Security equity(String price) {
        Security s = mock(Security.class);
        when(s.getAssetClass()).thenReturn(AssetClass.EQUITY);
        when(s.getCleanPrice()).thenReturn(new BigDecimal(price));
        return s;
    }

    private Position position(Security s, String netQty) {
        Position p = mock(Position.class);
        when(p.getSecurity()).thenReturn(s);
        when(p.getNetQuantity()).thenReturn(new BigDecimal(netQty));
        return p;
    }

    private Order order(String portfolio, Security s, String qty, String limitPrice) {
        Order o = mock(Order.class);
        when(o.getPortfolio()).thenReturn(portfolio);
        when(o.getSecurity()).thenReturn(s);
        when(o.getQuantity()).thenReturn(new BigDecimal(qty));
        when(o.getLimitPrice()).thenReturn(new BigDecimal(limitPrice));
        return o;
    }

    @Test
    void breachesWhenExistingPlusIncomingExceedsLimit() {
        limits.setMaxGrossNotional(new BigDecimal("10000000")); // $10MM desk limit
        Security sec = equity("100");
        // Existing gross: 60,000 * 100 = $6MM.
        List<Position> book = List.of(position(sec, "60000"));
        when(positions.forPortfolio("P")).thenReturn(book);
        // Incoming: 50,000 * 100 = $5MM → projected $11MM > $10MM.
        Order o = order("P", sec, "50000", "100");

        assertThat(guard.check(o)).isPresent();
        assertThat(guard.check(o).get()).contains("breach");
    }

    @Test
    void passesWhenWithinLimit() {
        limits.setMaxGrossNotional(new BigDecimal("10000000"));
        Security sec = equity("100");
        List<Position> book = List.of(position(sec, "60000")); // $6MM
        when(positions.forPortfolio("P")).thenReturn(book);
        Order o = order("P", sec, "30000", "100"); // +$3MM → $9MM ≤ $10MM

        assertThat(guard.check(o)).isEmpty();
    }

    @Test
    void nonPositiveLimitDisablesTheCheck() {
        limits.setMaxGrossNotional(BigDecimal.ZERO);
        Security sec = equity("100");
        List<Position> book = List.of(position(sec, "1000000000"));
        when(positions.forPortfolio("P")).thenReturn(book);
        Order o = order("P", sec, "1000000000", "100"); // enormous, but check is off

        assertThat(guard.check(o)).isEmpty();
    }
}
