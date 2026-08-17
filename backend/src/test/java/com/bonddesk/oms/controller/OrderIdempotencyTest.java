package com.bonddesk.oms.controller;

import com.bonddesk.oms.config.SecurityConfig;
import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.domain.TimeInForce;
import com.bonddesk.oms.idempotency.IdempotencyStore;
import com.bonddesk.oms.idempotency.InMemoryIdempotencyStore;
import com.bonddesk.oms.security.JwtService;
import com.bonddesk.oms.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * The Idempotency-Key contract on order creation: a retry replays the original order instead of creating
 * a second, the same key with a different body is rejected, and an absent key preserves the plain
 * create-every-time behaviour. Runs without a database — the order service is mocked and a real in-memory
 * idempotency store backs the flow.
 */
@WebMvcTest(OrderController.class)
@Import(SecurityConfig.class)
@WithMockUser(roles = "TRADER")   // create is a write — needs a role
class OrderIdempotencyTest {

    private static final String ORDER_A = """
            {"cusip":"912828YK0","portfolio":"P","trader":"t","side":"BUY",
             "orderType":"MARKET","timeInForce":"DAY","quantity":1000000}""";
    private static final String ORDER_B = """
            {"cusip":"912828YK0","portfolio":"P","trader":"t","side":"BUY",
             "orderType":"MARKET","timeInForce":"DAY","quantity":2000000}""";

    @TestConfiguration
    static class Stores {
        @Bean
        IdempotencyStore idempotencyStore() {
            return new InMemoryIdempotencyStore(60_000);
        }
    }

    @Autowired
    private MockMvc mvc;

    @MockBean
    private OrderService orders;

    @MockBean
    private JwtService jwt;

    @Test
    void aRetryWithTheSameKeyReplaysTheOriginalOrderInsteadOfCreatingASecond() throws Exception {
        Order o1 = order("ORDER-1");
        when(orders.create(any())).thenReturn(o1);
        when(orders.get("ORDER-1")).thenReturn(o1);

        mvc.perform(post("/api/orders").header("Idempotency-Key", "k-retry")
                        .contentType(MediaType.APPLICATION_JSON).content(ORDER_A))
                .andExpect(status().isCreated());

        // Same key, same body — the second call must not create again; it replays with 200.
        mvc.perform(post("/api/orders").header("Idempotency-Key", "k-retry")
                        .contentType(MediaType.APPLICATION_JSON).content(ORDER_A))
                .andExpect(status().isOk());

        verify(orders, times(1)).create(any());
        verify(orders, times(1)).get("ORDER-1");
    }

    @Test
    void reusingAKeyWithADifferentBodyIs422() throws Exception {
        Order o1 = order("ORDER-1");
        when(orders.create(any())).thenReturn(o1);

        mvc.perform(post("/api/orders").header("Idempotency-Key", "k-mismatch")
                        .contentType(MediaType.APPLICATION_JSON).content(ORDER_A))
                .andExpect(status().isCreated());

        mvc.perform(post("/api/orders").header("Idempotency-Key", "k-mismatch")
                        .contentType(MediaType.APPLICATION_JSON).content(ORDER_B))
                .andExpect(status().isUnprocessableEntity());

        verify(orders, times(1)).create(any());
    }

    @Test
    void withoutAKeyEveryRequestCreates() throws Exception {
        Order o1 = order("ORDER-1");
        Order o2 = order("ORDER-2");
        when(orders.create(any())).thenReturn(o1, o2);

        mvc.perform(post("/api/orders").contentType(MediaType.APPLICATION_JSON).content(ORDER_A))
                .andExpect(status().isCreated());
        mvc.perform(post("/api/orders").contentType(MediaType.APPLICATION_JSON).content(ORDER_A))
                .andExpect(status().isCreated());

        verify(orders, times(2)).create(any());
    }

    @Test
    void aFailedCreateReleasesTheKeySoTheClientCanRetry() throws Exception {
        Order o1 = order("ORDER-1");
        when(orders.create(any()))
                .thenThrow(new RuntimeException("compliance service down"))
                .thenReturn(o1);

        mvc.perform(post("/api/orders").header("Idempotency-Key", "k-failed")
                        .contentType(MediaType.APPLICATION_JSON).content(ORDER_A))
                .andExpect(status().isInternalServerError());

        // The reservation was released, so the same key can be retried and now succeeds (201, not replay).
        mvc.perform(post("/api/orders").header("Idempotency-Key", "k-failed")
                        .contentType(MediaType.APPLICATION_JSON).content(ORDER_A))
                .andExpect(status().isCreated());

        verify(orders, times(2)).create(any());
        verify(orders, never()).get(any());
    }

    private Order order(String ref) {
        Security sec = org.mockito.Mockito.mock(Security.class);
        Order o = org.mockito.Mockito.mock(Order.class);
        when(o.getOrderRef()).thenReturn(ref);
        when(o.getSecurity()).thenReturn(sec);
        when(o.getSide()).thenReturn(OrderSide.BUY);
        when(o.getOrderType()).thenReturn(OrderType.MARKET);
        when(o.getTimeInForce()).thenReturn(TimeInForce.DAY);
        when(o.getQuantity()).thenReturn(new BigDecimal("1000000"));
        when(o.getFilledQuantity()).thenReturn(BigDecimal.ZERO);
        when(o.getStatus()).thenReturn(OrderStatus.NEW);
        when(o.getExecutions()).thenReturn(java.util.List.of());
        return o;
    }
}
