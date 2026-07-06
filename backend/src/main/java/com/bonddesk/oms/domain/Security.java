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
 * Reference (static) data for a tradable security — a bond or a listed equity.
 *
 * <p>The CUSIP is used as the natural primary key: it is the industry-standard
 * 9-character identifier for a North American security (equities have CUSIPs too, e.g.
 * Apple is 037833100), so there is no benefit to a synthetic surrogate key here.
 *
 * <p>The {@link #assetClass} discriminates bonds from equities. Bond-specific fields
 * (coupon, maturity, rating) are null for equities; the equity {@link #ticker} is null
 * for bonds. This keeps one security master, one order model and one position model
 * across asset classes rather than parallel silos.
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

    /** Asset class — determines how the security is priced and executed. */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private AssetClass assetClass = AssetClass.FIXED_INCOME;

    /** Exchange ticker, e.g. "AAPL" — equities only (null for bonds). */
    @Column(length = 12)
    private String ticker;

    /** 12-character ISIN, e.g. "US912828YK08". */
    @Column(length = 12)
    private String isin;

    /** Human-readable description, e.g. "US TREASURY N/B 1.5% 2030". */
    @Column(nullable = false)
    private String description;

    /** Issuing entity, e.g. "US TREASURY" or "APPLE INC". */
    @Column(nullable = false)
    private String issuer;

    /** Annual coupon rate as a percentage, e.g. 1.5 means 1.50% — fixed income only. */
    @Column(precision = 7, scale = 4)
    private BigDecimal couponRate;

    /** Maturity date — fixed income only (null for equities). */
    private LocalDate maturityDate;

    /** Par/face value of a single bond, typically 1000 — fixed income only. */
    @Column(precision = 19, scale = 2)
    private BigDecimal faceValue;

    @Column(length = 3, nullable = false)
    private String currency;

    /** Sector classification, e.g. "SOVEREIGN", "CORPORATE", "MUNICIPAL". */
    @Column(nullable = false)
    private String sector;

    /** Credit rating — fixed income only (null for equities). */
    @Enumerated(EnumType.STRING)
    private CreditRating rating;

    /**
     * Latest indicative reference price. For bonds this is the clean price as a
     * percentage of par (e.g. 99.75 = 99.75% of face); for equities it is the price in
     * currency per share. Used as a fallback fill reference before a live quote arrives.
     */
    @Column(nullable = false, precision = 9, scale = 4)
    private BigDecimal cleanPrice;

    /** When true, the desk is prohibited from trading this security (restricted list). */
    @Column(nullable = false)
    private boolean restricted = false;
}
