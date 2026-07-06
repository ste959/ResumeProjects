package com.bonddesk.oms.util;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Security;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The cash notional of a trade depends on the asset class's quoting convention: bonds are
 * a percentage of par (divide by 100), equities are currency per share (no divide).
 */
class PricingTest {

    private static Security security(AssetClass assetClass) {
        Security s = new Security();
        s.setAssetClass(assetClass);
        s.setCusip("TEST");
        return s;
    }

    @Test
    void bondNotionalIsPercentOfPar() {
        Security bond = security(AssetClass.FIXED_INCOME);
        // 1,000,000 face at 99.00% of par = 990,000 cash.
        assertThat(Pricing.notional(bond, new BigDecimal("1000000"), new BigDecimal("99.00")))
                .isEqualByComparingTo("990000.00");
    }

    @Test
    void equityNotionalIsSharesTimesPrice() {
        Security equity = security(AssetClass.EQUITY);
        // 5 shares at $312.50 = $1,562.50 (no division by par).
        assertThat(Pricing.notional(equity, new BigDecimal("5"), new BigDecimal("312.50")))
                .isEqualByComparingTo("1562.50");
    }
}
