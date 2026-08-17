package com.bonddesk.oms.controller;

import com.bonddesk.oms.AbstractPostgresIntegrationTest;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.OrderType;
import com.bonddesk.oms.domain.TimeInForce;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.math.BigDecimal;

import static org.hamcrest.Matchers.greaterThanOrEqualTo;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@AutoConfigureMockMvc
@org.springframework.security.test.context.support.WithMockUser(roles = "TRADER")   // writes need a role
class OrderControllerIntegrationTest extends AbstractPostgresIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper json;

    private String body(String cusip, OrderSide side, OrderType type, String qty, BigDecimal limit) {
        try {
            return json.writeValueAsString(new CreateOrderRequest(
                    cusip, "PORT-WEB", "trader1", side, type, TimeInForce.DAY, new BigDecimal(qty), limit));
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private String createOrderRef(String cusip) throws Exception {
        MvcResult res = mvc.perform(post("/api/orders").contentType(MediaType.APPLICATION_JSON)
                        .content(body(cusip, OrderSide.BUY, OrderType.MARKET, "1000000", null)))
                .andExpect(status().isCreated())
                .andReturn();
        return json.readTree(res.getResponse().getContentAsString()).get("orderRef").asText();
    }

    @Test
    void createValidOrderReturns201WithLocation() throws Exception {
        mvc.perform(post("/api/orders").contentType(MediaType.APPLICATION_JSON)
                        .content(body("912828YK0", OrderSide.BUY, OrderType.MARKET, "1000000", null)))
                .andExpect(status().isCreated())
                .andExpect(header().exists("Location"))
                .andExpect(jsonPath("$.status").value("NEW"))
                .andExpect(jsonPath("$.cusip").value("912828YK0"))
                .andExpect(jsonPath("$.remainingQuantity").value(1000000));
    }

    @Test
    void invalidPayloadReturns400WithFieldErrors() throws Exception {
        // quantity below the minimum (must be >= 1) and a blank trader
        String bad = """
                {"cusip":"912828YK0","portfolio":"P","trader":"","side":"BUY",
                 "orderType":"MARKET","timeInForce":"DAY","quantity":0}""";
        mvc.perform(post("/api/orders").contentType(MediaType.APPLICATION_JSON).content(bad))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fieldErrors.quantity").exists())
                .andExpect(jsonPath("$.fieldErrors.trader").exists());
    }

    @Test
    void limitOrderWithoutPriceReturns400() throws Exception {
        mvc.perform(post("/api/orders").contentType(MediaType.APPLICATION_JSON)
                        .content(body("912828YK0", OrderSide.BUY, OrderType.LIMIT, "1000000", null)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("limitPrice is required for LIMIT orders"));
    }

    @Test
    void restrictedSecurityIsPersistedAsRejected() throws Exception {
        mvc.perform(post("/api/orders").contentType(MediaType.APPLICATION_JSON)
                        .content(body("999999XX9", OrderSide.BUY, OrderType.MARKET, "1000000", null)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("REJECTED"))
                .andExpect(jsonPath("$.statusReason").exists());
    }

    @Test
    void blotterListsOrders() throws Exception {
        createOrderRef("912828YK0");
        mvc.perform(get("/api/orders"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(greaterThanOrEqualTo(1))));
    }

    @Test
    void fetchingUnknownOrderReturns404() throws Exception {
        mvc.perform(get("/api/orders/does-not-exist"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void endToEndStageRouteFillUpdatesPositions() throws Exception {
        String ref = createOrderRef("91282CFX4");

        mvc.perform(post("/api/orders/{ref}/stage", ref)).andExpect(status().isOk());
        mvc.perform(post("/api/orders/{ref}/route", ref)).andExpect(status().isOk());

        mvc.perform(post("/api/orders/{ref}/fills", ref).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"quantity\":1000000,\"price\":99.5,\"venue\":\"TW\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("FILLED"));

        mvc.perform(get("/api/portfolios/{portfolio}/positions", "PORT-WEB"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.cusip=='91282CFX4')].netQuantity").value(hasSize(1)));
    }

    @Test
    void routingBeforeStagingReturns409() throws Exception {
        String ref = createOrderRef("912828YK0");
        mvc.perform(post("/api/orders/{ref}/route", ref))
                .andExpect(status().isConflict());
    }

    @Test
    void corsPreflightAllowsBrowserOriginOnAnyLocalhostPort() throws Exception {
        // The UI is served from nginx on :8088 (not the Vite :5173 dev port), so the
        // browser's Origin must be accepted or every write returns 403.
        mvc.perform(options("/api/orders")
                        .header("Origin", "http://localhost:8088")
                        .header("Access-Control-Request-Method", "POST"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:8088"));
    }

    @Test
    void rootReturnsServiceInfo() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.service").value("BondDesk OMS"))
                .andExpect(jsonPath("$.links.apiDocs").exists());
    }

    @Test
    void unmappedPathReturns404NotServerError() throws Exception {
        mvc.perform(get("/no/such/path"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }
}
