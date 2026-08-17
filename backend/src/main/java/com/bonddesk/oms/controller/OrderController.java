package com.bonddesk.oms.controller;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.dto.CancelRequest;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.bonddesk.oms.dto.FillRequest;
import com.bonddesk.oms.dto.OrderResponse;
import com.bonddesk.oms.service.OrderService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.util.List;

/** Order entry and lifecycle actions — the trader blotter's backend. */
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders", description = "Stage, route, fill and cancel fixed-income orders")
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    @Operation(summary = "List orders (the blotter), optionally filtered by status or portfolio")
    public List<OrderResponse> list(@RequestParam(required = false) OrderStatus status,
                                    @RequestParam(required = false) String portfolio) {
        return orders.list(status, portfolio).stream().map(OrderResponse::from).toList();
    }

    @GetMapping("/{orderRef}")
    @Operation(summary = "Fetch a single order with its fills")
    public OrderResponse get(@PathVariable String orderRef) {
        return OrderResponse.from(orders.get(orderRef));
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping
    @Operation(summary = "Stage a new order (runs pre-trade compliance at entry)")
    public ResponseEntity<OrderResponse> create(@Valid @RequestBody CreateOrderRequest request,
                                                UriComponentsBuilder uri) {
        Order order = orders.create(request);
        URI location = uri.path("/api/orders/{ref}").buildAndExpand(order.getOrderRef()).toUri();
        return ResponseEntity.created(location).body(OrderResponse.from(order));
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{orderRef}/stage")
    @Operation(summary = "Release the order to be worked (NEW → STAGED)")
    public OrderResponse stage(@PathVariable String orderRef) {
        return OrderResponse.from(orders.stage(orderRef));
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{orderRef}/route")
    @Operation(summary = "Route the order to an execution venue (STAGED → ROUTED)")
    public OrderResponse route(@PathVariable String orderRef) {
        return OrderResponse.from(orders.route(orderRef));
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{orderRef}/fills")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Report a fill against a working order")
    public OrderResponse fill(@PathVariable String orderRef, @Valid @RequestBody FillRequest request) {
        return OrderResponse.from(
                orders.recordFill(orderRef, request.quantity(), request.price(), request.venueOrDefault()));
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping("/{orderRef}/cancel")
    @Operation(summary = "Cancel a non-terminal order")
    public OrderResponse cancel(@PathVariable String orderRef,
                                @RequestBody(required = false) CancelRequest request) {
        return OrderResponse.from(orders.cancel(orderRef, request == null ? null : request.reason()));
    }
}
