package com.bonddesk.oms.config;

import com.bonddesk.oms.controller.OrderController;
import com.bonddesk.oms.idempotency.IdempotencyStore;
import com.bonddesk.oms.security.JwtService;
import com.bonddesk.oms.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * RBAC wiring, verified without a database: reads are public, but a write needs a role — unauthenticated
 * is 401 and a VIEWER is 403. (The TRADER-can-write positive path runs in OrderControllerIntegrationTest.)
 */
@WebMvcTest(OrderController.class)
@Import(SecurityConfig.class)
class OrderControllerSecurityTest {

    @Autowired
    private MockMvc mvc;

    @MockBean
    private OrderService orders;

    @MockBean
    private JwtService jwt;   // SecurityConfig's filter chain needs it; unused under @WithMockUser

    @MockBean
    private IdempotencyStore idempotency;   // OrderController collaborator; unused on these paths

    @Test
    void unauthenticatedWriteIsUnauthorized() throws Exception {
        mvc.perform(post("/api/orders/{ref}/stage", "O1")).andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCannotWrite() throws Exception {
        mvc.perform(post("/api/orders/{ref}/stage", "O1")).andExpect(status().isForbidden());
    }

    @Test
    void readsArePublic() throws Exception {
        when(orders.list(any(), any())).thenReturn(List.of());
        mvc.perform(get("/api/orders")).andExpect(status().isOk());
    }
}
