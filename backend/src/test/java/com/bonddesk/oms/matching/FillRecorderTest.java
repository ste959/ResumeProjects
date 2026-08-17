package com.bonddesk.oms.matching;

import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.exception.InvalidStateTransitionException;
import com.bonddesk.oms.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.dao.OptimisticLockingFailureException;

import java.math.BigDecimal;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** The fill-recording failure policy: expected races don't retry, lock conflicts do, nothing is silent. */
class FillRecorderTest {

    private final OrderService orders = mock(OrderService.class);
    private final FillRecorder recorder = new FillRecorder(orders);

    private DeskFillEvent fill() {
        return new DeskFillEvent("O1", BigDecimal.ONE, BigDecimal.TEN, "VENUE");
    }

    @Test
    void recordsOnceOnSuccess() {
        when(orders.recordFill(anyString(), any(), any(), anyString())).thenReturn(null);
        recorder.onDeskFill(fill());
        verify(orders, times(1)).recordFill(anyString(), any(), any(), anyString());
    }

    @Test
    void doesNotRetryTheExpectedStateRace() {
        when(orders.recordFill(anyString(), any(), any(), anyString()))
                .thenThrow(new InvalidStateTransitionException("O1", OrderStatus.CANCELLED, OrderStatus.FILLED));
        recorder.onDeskFill(fill());
        verify(orders, times(1)).recordFill(anyString(), any(), any(), anyString());     // already-terminal → give up
    }

    @Test
    void retriesAnOptimisticLockConflict() {
        when(orders.recordFill(anyString(), any(), any(), anyString()))
                .thenThrow(new OptimisticLockingFailureException("version race"));
        recorder.onDeskFill(fill());
        verify(orders, times(3)).recordFill(anyString(), any(), any(), anyString());     // MAX_ATTEMPTS
    }
}
