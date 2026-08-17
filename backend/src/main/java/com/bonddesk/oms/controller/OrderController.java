package com.bonddesk.oms.controller;

import com.bonddesk.oms.domain.Order;
import com.bonddesk.oms.domain.OrderStatus;
import com.bonddesk.oms.dto.CancelRequest;
import com.bonddesk.oms.dto.CreateOrderRequest;
import com.bonddesk.oms.dto.FillRequest;
import com.bonddesk.oms.dto.OrderResponse;
import com.bonddesk.oms.dto.OrderSummaryResponse;
import com.bonddesk.oms.dto.PagedResponse;
import com.bonddesk.oms.exception.IdempotencyConflictException;
import com.bonddesk.oms.exception.IdempotencyMismatchException;
import com.bonddesk.oms.idempotency.IdempotencyStore;
import com.bonddesk.oms.service.OrderService;
import com.fasterxml.jackson.databind.ObjectMapper;
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
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;
import java.security.MessageDigest;
import java.util.HexFormat;

/** Order entry and lifecycle actions — the trader blotter's backend. */
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders", description = "Stage, route, fill and cancel fixed-income orders")
public class OrderController {

    private final OrderService orders;
    private final IdempotencyStore idempotency;
    private final ObjectMapper json;

    public OrderController(OrderService orders, IdempotencyStore idempotency, ObjectMapper json) {
        this.orders = orders;
        this.idempotency = idempotency;
        this.json = json;
    }

    @GetMapping
    @Operation(summary = "List orders (the blotter) as a keyset page, newest first. Filter by status or "
            + "portfolio; pass the previous page's nextCursor to page on.")
    public PagedResponse<OrderSummaryResponse> list(
            @RequestParam(required = false) OrderStatus status,
            @RequestParam(required = false) String portfolio,
            @RequestParam(required = false) String cursor,
            @RequestParam(defaultValue = "50") int size) {
        return orders.listPage(status, portfolio, cursor, size);
    }

    @GetMapping("/{orderRef}")
    @Operation(summary = "Fetch a single order with its fills")
    public OrderResponse get(@PathVariable String orderRef) {
        return OrderResponse.from(orders.get(orderRef));
    }

    @PreAuthorize("hasAnyRole('TRADER','ADMIN','SERVICE')")
    @PostMapping
    @Operation(summary = "Stage a new order (runs pre-trade compliance at entry). "
            + "Send an Idempotency-Key header to make a retry safe.")
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey,
            UriComponentsBuilder uri) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return created(orders.create(request), uri);   // unguarded — legacy/simple clients
        }

        IdempotencyStore.Reservation reservation = idempotency.begin(idempotencyKey, fingerprint(request));
        if (reservation instanceof IdempotencyStore.Reservation.Replay replay) {
            // A retry of an already-completed request: return the original order, don't create a second.
            return ResponseEntity.ok(OrderResponse.from(orders.get(replay.result())));
        }
        if (reservation instanceof IdempotencyStore.Reservation.Mismatch) {
            throw new IdempotencyMismatchException("Idempotency-Key was already used with a different request");
        }
        if (reservation instanceof IdempotencyStore.Reservation.InFlight) {
            throw new IdempotencyConflictException("A request with this Idempotency-Key is still processing");
        }
        // Acquired — we own the key. Do the work, record the outcome, and release the key if it fails so
        // the client can retry rather than being permanently blocked by a half-finished reservation.
        try {
            Order order = orders.create(request);
            idempotency.complete(idempotencyKey, order.getOrderRef());
            return created(order, uri);
        } catch (RuntimeException e) {
            idempotency.release(idempotencyKey);
            throw e;
        }
    }

    private ResponseEntity<OrderResponse> created(Order order, UriComponentsBuilder uri) {
        URI location = uri.path("/api/orders/{ref}").buildAndExpand(order.getOrderRef()).toUri();
        return ResponseEntity.created(location).body(OrderResponse.from(order));
    }

    /** A stable hash of the request body, so the same key with a different body is caught (422). */
    private String fingerprint(CreateOrderRequest request) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(json.writeValueAsBytes(request));
            return HexFormat.of().formatHex(digest);
        } catch (Exception e) {
            // Fingerprinting must never block an order; degrade to plain key-based dedup on failure.
            return "unfingerprinted";
        }
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
