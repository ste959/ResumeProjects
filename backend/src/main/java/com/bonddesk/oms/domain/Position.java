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
import jakarta.persistence.UniqueConstraint;
import jakarta.persistence.Version;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * The desk's holding of a single security in a single portfolio, maintained
 * incrementally as executions arrive. Uniquely keyed by (portfolio, security).
 *
 * <p>{@code netQuantity} is signed par/face notional: positive is long, negative short.
 * {@code avgCost} is the quantity-weighted average entry price (% of par) of the
 * current long or short position.
 */
@Entity
@Table(name = "positions", uniqueConstraints =
        @UniqueConstraint(name = "uq_position_portfolio_cusip", columnNames = {"portfolio", "cusip"}))
@Getter
@Setter
@NoArgsConstructor
public class Position {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String portfolio;

    @ManyToOne(fetch = FetchType.EAGER, optional = false)
    @JoinColumn(name = "cusip", nullable = false)
    private Security security;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal netQuantity = BigDecimal.ZERO;

    @Column(nullable = false, precision = 9, scale = 4)
    private BigDecimal avgCost = BigDecimal.ZERO;

    @Column(nullable = false)
    private Instant updatedAt;

    @Version
    private Long version;

    public Position(String portfolio, Security security) {
        this.portfolio = portfolio;
        this.security = security;
    }
}
