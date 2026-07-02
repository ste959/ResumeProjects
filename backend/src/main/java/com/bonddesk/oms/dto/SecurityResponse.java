package com.bonddesk.oms.dto;

import com.bonddesk.oms.domain.CreditRating;
import com.bonddesk.oms.domain.Security;

import java.math.BigDecimal;
import java.time.LocalDate;

public record SecurityResponse(
        String cusip,
        String isin,
        String description,
        String issuer,
        BigDecimal couponRate,
        LocalDate maturityDate,
        BigDecimal faceValue,
        String currency,
        String sector,
        CreditRating rating,
        boolean investmentGrade,
        BigDecimal cleanPrice,
        boolean restricted
) {

    public static SecurityResponse from(Security s) {
        return new SecurityResponse(
                s.getCusip(),
                s.getIsin(),
                s.getDescription(),
                s.getIssuer(),
                s.getCouponRate(),
                s.getMaturityDate(),
                s.getFaceValue(),
                s.getCurrency(),
                s.getSector(),
                s.getRating(),
                s.getRating().isInvestmentGrade(),
                s.getCleanPrice(),
                s.isRestricted()
        );
    }
}
