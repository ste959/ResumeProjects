package com.bonddesk.oms.domain;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderStatusTest {

    @Test
    void happyPathTransitionsAreAllowed() {
        assertThat(OrderStatus.NEW.canTransitionTo(OrderStatus.STAGED)).isTrue();
        assertThat(OrderStatus.STAGED.canTransitionTo(OrderStatus.ROUTED)).isTrue();
        assertThat(OrderStatus.ROUTED.canTransitionTo(OrderStatus.PARTIALLY_FILLED)).isTrue();
        assertThat(OrderStatus.ROUTED.canTransitionTo(OrderStatus.FILLED)).isTrue();
        assertThat(OrderStatus.PARTIALLY_FILLED.canTransitionTo(OrderStatus.FILLED)).isTrue();
    }

    @Test
    void skippingStatesIsRejected() {
        assertThat(OrderStatus.NEW.canTransitionTo(OrderStatus.ROUTED)).isFalse();
        assertThat(OrderStatus.STAGED.canTransitionTo(OrderStatus.FILLED)).isFalse();
        assertThat(OrderStatus.NEW.canTransitionTo(OrderStatus.PARTIALLY_FILLED)).isFalse();
    }

    @Test
    void workingOrdersCanBeCancelled() {
        assertThat(OrderStatus.NEW.canTransitionTo(OrderStatus.CANCELLED)).isTrue();
        assertThat(OrderStatus.STAGED.canTransitionTo(OrderStatus.CANCELLED)).isTrue();
        assertThat(OrderStatus.ROUTED.canTransitionTo(OrderStatus.CANCELLED)).isTrue();
        assertThat(OrderStatus.PARTIALLY_FILLED.canTransitionTo(OrderStatus.CANCELLED)).isTrue();
    }

    @Test
    void terminalStatesAllowNoTransitions() {
        for (OrderStatus terminal : OrderStatus.TERMINAL) {
            assertThat(terminal.isTerminal()).isTrue();
            assertThat(terminal.allowedTransitions()).isEmpty();
        }
    }

    @Test
    void filledOrderCannotBeCancelled() {
        assertThat(OrderStatus.FILLED.canTransitionTo(OrderStatus.CANCELLED)).isFalse();
    }
}
