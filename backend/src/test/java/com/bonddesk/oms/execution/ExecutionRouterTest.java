package com.bonddesk.oms.execution;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.equities.AlpacaExecutionVenue;
import com.bonddesk.oms.matching.MatchingService;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

/**
 * The router must send each order to the venue for its asset class, and degrade to a
 * no-op when a venue is absent (module disabled) rather than failing the order.
 */
class ExecutionRouterTest {

    private static Order order(AssetClass assetClass) {
        Security s = new Security();
        s.setAssetClass(assetClass);
        s.setCusip("TEST");
        Order o = new Order();
        o.setSecurity(s);
        o.setOrderRef("ref-1");
        return o;
    }

    @Test
    void equityOrdersGoToTheEquityVenue() {
        MatchingService clob = mock(MatchingService.class);
        AlpacaExecutionVenue equities = mock(AlpacaExecutionVenue.class);
        ExecutionRouter router = new ExecutionRouter(Optional.of(clob), Optional.of(equities));

        Order o = order(AssetClass.EQUITY);
        router.route(o);

        verify(equities).route(o);
        verify(clob, never()).route(any());
    }

    @Test
    void fixedIncomeOrdersGoToTheClob() {
        MatchingService clob = mock(MatchingService.class);
        AlpacaExecutionVenue equities = mock(AlpacaExecutionVenue.class);
        ExecutionRouter router = new ExecutionRouter(Optional.of(clob), Optional.of(equities));

        Order o = order(AssetClass.FIXED_INCOME);
        router.route(o);

        verify(clob).route(o);
        verify(equities, never()).route(any());
    }

    @Test
    void missingVenueDegradesToNoOp() {
        ExecutionRouter router = new ExecutionRouter(Optional.empty(), Optional.empty());
        assertThatCode(() -> router.route(order(AssetClass.EQUITY))).doesNotThrowAnyException();
        assertThatCode(() -> router.route(order(AssetClass.FIXED_INCOME))).doesNotThrowAnyException();
    }
}
