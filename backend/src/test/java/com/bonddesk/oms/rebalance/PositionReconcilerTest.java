package com.bonddesk.oms.rebalance;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.equities.AlpacaBrokerClient;
import com.bonddesk.oms.equities.AlpacaBrokerClient.BrokerPosition;
import com.bonddesk.oms.repository.SecurityRepository;
import com.bonddesk.oms.service.PositionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Unit tests for the broker → OMS position reconciler with all collaborators mocked: broker
 * positions are snapped (signed) onto the OMS book, stale OMS equity positions are flattened, and
 * unknown broker symbols are skipped — with a hard no-op when credentials are absent.
 */
class PositionReconcilerTest {

    private static final String PORTFOLIO = "EQUITY-PAPER";

    private AlpacaBrokerClient broker;
    private SecurityRepository securities;
    private PositionService positions;
    private RebalanceProperties props;
    private PositionReconciler reconciler;

    @BeforeEach
    void setUp() {
        broker = mock(AlpacaBrokerClient.class);
        securities = mock(SecurityRepository.class);
        positions = mock(PositionService.class);
        props = mock(RebalanceProperties.class);
        reconciler = new PositionReconciler(broker, securities, positions, props);
        when(props.getPortfolio()).thenReturn(PORTFOLIO);
    }

    private Security equity(String ticker) {
        Security s = mock(Security.class);
        when(s.getTicker()).thenReturn(ticker);
        when(s.getAssetClass()).thenReturn(AssetClass.EQUITY);
        return s;
    }

    private Position position(Security sec, String netQty) {
        Position p = mock(Position.class);
        when(p.getSecurity()).thenReturn(sec);
        when(p.getNetQuantity()).thenReturn(new BigDecimal(netQty));
        return p;
    }

    @Test
    void snapsSignedBrokerPositionsFlattensStaleAndSkipsUnknown() {
        Security aapl = equity("AAPL");
        Security msft = equity("MSFT");
        Security nvda = equity("NVDA");

        when(broker.brokerReachable()).thenReturn(true);
        when(broker.positions()).thenReturn(List.of(
                new BrokerPosition("AAPL", new BigDecimal("10"), new BigDecimal("190.00")),
                new BrokerPosition("MSFT", new BigDecimal("-5"), new BigDecimal("300.00")),
                new BrokerPosition("ZZZZ", new BigDecimal("2"), new BigDecimal("50.00"))));

        when(securities.findByTicker("AAPL")).thenReturn(Optional.of(aapl));
        when(securities.findByTicker("MSFT")).thenReturn(Optional.of(msft));
        when(securities.findByTicker("ZZZZ")).thenReturn(Optional.empty());

        // OMS holds NVDA +3, which the broker no longer has → must be flattened.
        // Build the position before stubbing so the nested mock setup doesn't interrupt when().
        Position nvdaPos = position(nvda, "3");
        when(positions.forPortfolio(PORTFOLIO)).thenReturn(List.of(nvdaPos));

        ReconcileSummary summary = reconciler.reconcile();

        assertThat(summary.updated()).isEqualTo(2);
        assertThat(summary.flattened()).isEqualTo(1);
        assertThat(summary.unknown()).isEqualTo(1);

        verify(positions).setPosition(eq(PORTFOLIO), eq(aapl),
                eq(new BigDecimal("10")), eq(new BigDecimal("190.00")));
        verify(positions).setPosition(eq(PORTFOLIO), eq(msft),
                eq(new BigDecimal("-5")), eq(new BigDecimal("300.00")));
        verify(positions).setPosition(eq(PORTFOLIO), eq(nvda),
                eq(BigDecimal.ZERO), eq(BigDecimal.ZERO));
    }

    @Test
    void noOpWithoutCredentials() {
        when(broker.brokerReachable()).thenReturn(false);

        ReconcileSummary summary = reconciler.reconcile();

        assertThat(summary.updated()).isZero();
        assertThat(summary.flattened()).isZero();
        assertThat(summary.unknown()).isZero();
        verifyNoInteractions(positions);
        verifyNoInteractions(securities);
    }
}
