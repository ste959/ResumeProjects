package com.bonddesk.oms.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * A single fill (partial or full) against an {@link Order}, as reported back from an
 * execution venue. An order accumulates one or more executions over its life.
 */
@Entity
@Table(name = "execution")
@Getter
@Setter
@NoArgsConstructor
public class Execution {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    /** Par/face notional filled by this execution. */
    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal quantity;

    /** Execution price as % of par. */
    @Column(nullable = false, precision = 9, scale = 4)
    private BigDecimal price;

    /** Venue that reported the fill, e.g. "TW" (Tradeweb), "BLBG" (Bloomberg), "SIM". */
    @Column(nullable = false, length = 16)
    private String venue;

    @Column(nullable = false)
    private Instant executedAt;

    public Execution(BigDecimal quantity, BigDecimal price, String venue, Instant executedAt) {
        this.quantity = quantity;
        this.price = price;
        this.venue = venue;
        this.executedAt = executedAt;
    }
}
