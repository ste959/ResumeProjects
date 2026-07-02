package com.bonddesk.oms.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * A fixed-income order working through its lifecycle on the desk.
 *
 * <p>Quantity is expressed as <em>par/face notional</em> (e.g. {@code 1000000} = $1MM
 * face). Prices are quoted as a percentage of par (e.g. {@code 99.75} = 99.75% of face),
 * the market convention for bonds.
 */
@Entity
@Table(name = "orders")
@Getter
@Setter
@NoArgsConstructor
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** Stable, externally shared identifier (UUID). Assigned at creation. */
    @Column(name = "order_ref", nullable = false, unique = true, updatable = false, length = 36)
    private String orderRef;

    @ManyToOne(fetch = FetchType.EAGER, optional = false)
    @JoinColumn(name = "cusip", nullable = false)
    private Security security;

    /** Portfolio / account the order is being traded for. */
    @Column(nullable = false)
    private String portfolio;

    /** Trader who entered the order. */
    @Column(nullable = false)
    private String trader;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderSide side;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderType orderType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private TimeInForce timeInForce;

    /** Par/face notional requested. */
    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal quantity;

    /** Limit price as % of par; null for MARKET orders. */
    @Column(precision = 9, scale = 4)
    private BigDecimal limitPrice;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.NEW;

    /** Par/face notional filled so far. */
    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal filledQuantity = BigDecimal.ZERO;

    /** Quantity-weighted average fill price as % of par; null until first fill. */
    @Column(precision = 9, scale = 4)
    private BigDecimal avgFillPrice;

    /** Populated when the order is REJECTED or CANCELLED. */
    @Column(length = 500)
    private String statusReason;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    /** Optimistic-lock guard against concurrent fills/cancels on the same order. */
    @Version
    private Long version;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.LAZY)
    @OrderBy("executedAt ASC")
    private List<Execution> executions = new ArrayList<>();

    /** Par/face notional still working in the market. */
    public BigDecimal remainingQuantity() {
        return quantity.subtract(filledQuantity);
    }

    public boolean isFullyFilled() {
        return filledQuantity.compareTo(quantity) >= 0;
    }

    public void addExecution(Execution execution) {
        execution.setOrder(this);
        executions.add(execution);
    }
}
