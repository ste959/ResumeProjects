package com.bonddesk.oms.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * Reference (static) data for a tradable fixed-income instrument — a bond.
 *
 * <p>The CUSIP is used as the natural primary key: it is the industry-standard
 * 9-character identifier for a North American security, so there is no benefit to a
 * synthetic surrogate key here.
 */
@Entity
@Table(name = "security")
@Getter
@Setter
@NoArgsConstructor
public class Security {

    /** 9-character CUSIP, e.g. "912828YK0". */
    @Id
    @Column(length = 9, nullable = false)
    private String cusip;

    /** 12-character ISIN, e.g. "US912828YK08". */
    @Column(length = 12)
    private String isin;

    /** Human-readable description, e.g. "US TREASURY N/B 1.5% 2030". */
    @Column(nullable = false)
    private String description;

    /** Issuing entity, e.g. "US TREASURY" or "APPLE INC". */
    @Column(nullable = false)
    private String issuer;

    /** Annual coupon rate as a percentage, e.g. 1.5 means 1.50%. */
    @Column(nullable = false, precision = 7, scale = 4)
    private BigDecimal couponRate;

    @Column(nullable = false)
    private LocalDate maturityDate;

    /** Par/face value of a single bond, typically 1000. */
    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal faceValue;

    @Column(length = 3, nullable = false)
    private String currency;

    /** Sector classification, e.g. "SOVEREIGN", "CORPORATE", "MUNICIPAL". */
    @Column(nullable = false)
    private String sector;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private CreditRating rating;

    /**
     * Latest indicative clean price as a percentage of par (e.g. 99.75 = 99.75% of
     * face). Used by the execution simulator as a reference for fills.
     */
    @Column(nullable = false, precision = 9, scale = 4)
    private BigDecimal cleanPrice;

    /** When true, the desk is prohibited from trading this security (restricted list). */
    @Column(nullable = false)
    private boolean restricted = false;
}
