package com.bonddesk.oms.fixedincome;

import com.bonddesk.oms.domain.CreditRating;
import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Security;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Random;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The dealer engine must price off the curve + credit spread and surface the best
 * execution: the lowest offer when buying, the highest bid when selling.
 */
class DealerQuoteEngineTest {

    private DealerQuoteEngine engine;

    @BeforeEach
    void setUp() {
        FixedIncomeProperties props = new FixedIncomeProperties();
        props.setDealerCount(5);
        Clock clock = Clock.fixed(Instant.parse("2026-07-06T00:00:00Z"), ZoneOffset.UTC);
        // Uses the deterministic fallback curve (no network).
        YieldCurveService curve = new YieldCurveService(props, clock);
        engine = new DealerQuoteEngine(curve, new CreditSpreadModel(), props, clock);
    }

    private static Security corporate(CreditRating rating) {
        Security s = new Security();
        s.setCusip("TESTBBB01");
        s.setSector("CORPORATE");
        s.setRating(rating);
        s.setCouponRate(new BigDecimal("4.0000"));
        s.setMaturityDate(LocalDate.of(2034, 2, 15));
        return s;
    }

    @Test
    void buyTakesTheLowestOfferAndSellTheHighestBid() {
        Security bond = corporate(CreditRating.BBB);

        QuoteSet buy = engine.quote(bond, OrderSide.BUY, new BigDecimal("1000000"), new Random(1));
        assertThat(buy.quotes()).hasSize(5);
        assertThat(buy.quotes().stream().filter(DealerQuote::best).count()).isEqualTo(1);
        DealerQuote bestBuy = buy.quotes().stream().filter(DealerQuote::best).findFirst().orElseThrow();
        assertThat(buy.quotes()).allSatisfy(q ->
                assertThat(bestBuy.price()).isLessThanOrEqualTo(q.price())); // cheapest offer

        QuoteSet sell = engine.quote(bond, OrderSide.SELL, new BigDecimal("1000000"), new Random(1));
        DealerQuote bestSell = sell.quotes().stream().filter(DealerQuote::best).findFirst().orElseThrow();
        assertThat(sell.quotes()).allSatisfy(q ->
                assertThat(bestSell.price()).isGreaterThanOrEqualTo(q.price())); // highest bid
    }

    @Test
    void corporateTradesAtAPositiveSpreadOverTheCurve() {
        QuoteSet q = engine.quote(corporate(CreditRating.BBB), OrderSide.BUY,
                new BigDecimal("1000000"), new Random(7));
        assertThat(q.creditSpreadBps().doubleValue()).isEqualTo(135.0); // BBB from CreditSpreadModel
        assertThat(q.fairYieldPct().doubleValue()).isGreaterThan(q.curveYieldPct().doubleValue());
        assertThat(q.fairClean().doubleValue()).isPositive();
    }

    @Test
    void treasuriesPriceOnTheCurveWithNoCreditSpread() {
        Security ust = new Security();
        ust.setCusip("UST0000001");
        ust.setSector("SOVEREIGN");
        ust.setRating(CreditRating.AAA);
        ust.setCouponRate(new BigDecimal("4.0000"));
        ust.setMaturityDate(LocalDate.of(2034, 2, 15));

        QuoteSet q = engine.quote(ust, OrderSide.BUY, new BigDecimal("1000000"), new Random(3));
        assertThat(q.creditSpreadBps().doubleValue()).isEqualTo(0.0);
    }
}
