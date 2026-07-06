package com.bonddesk.oms.fixedincome;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.pricing.BondMath;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Simulates a fixed-income RFQ: several dealers respond with firm two-way prices around a
 * fair value derived from the real Treasury curve plus a credit spread. Each dealer adds
 * its own bid/offer, an inventory axe, and a little noise, so quotes disperse the way a
 * real request-for-quote does — and the client takes the best execution.
 *
 * <p>This is the market structure fixed income actually has (OTC, dealer-quoted), rather
 * than the lit central order book used for equities and crypto.
 */
@Component
public class DealerQuoteEngine {

    /** Dealer names kept within the execution-venue column width (16 chars). */
    private static final String[] DEALERS =
            {"Goldman Sachs", "JPMorgan", "Morgan Stanley", "Barclays", "Citadel", "Nomura"};

    private final YieldCurveService curveService;
    private final CreditSpreadModel spreads;
    private final FixedIncomeProperties props;
    private final Clock clock;

    public DealerQuoteEngine(YieldCurveService curveService, CreditSpreadModel spreads,
                             FixedIncomeProperties props, Clock clock) {
        this.curveService = curveService;
        this.spreads = spreads;
        this.props = props;
        this.clock = clock;
    }

    public QuoteSet quote(Security security, OrderSide side, BigDecimal quantity, Random rng) {
        LocalDate settlement = LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC);
        LocalDate maturity = security.getMaturityDate();
        double tenor = (maturity.toEpochDay() - settlement.toEpochDay()) / 365.25;

        YieldCurve curve = curveService.current();
        double curveYield = curve.interpolate(tenor);                 // percent
        double creditBps = spreads.spreadBps(security);
        double coupon = security.getCouponRate().doubleValue() / 100.0;
        double fairYield = curveYield / 100.0 + creditBps / 10_000.0; // decimal
        double fairClean = BondMath.cleanPriceFromYield(settlement, maturity, coupon, fairYield);
        double notional = quantity.doubleValue() * fairClean / 100.0;

        double half = halfSpreadBps(creditBps, notional);             // bid/offer half-spread, bps of yield
        int n = Math.min(props.getDealerCount(), DEALERS.length);

        // Price every dealer, then mark the best execution for the client's side.
        double[] prices = new double[n];
        double[] yields = new double[n];
        for (int i = 0; i < n; i++) {
            double axe = uniform(rng, -4, 4);      // dealer inventory tilt, bps
            double noise = uniform(rng, -1.5, 1.5); // idiosyncratic noise, bps
            // Client BUY lifts the offer (lower yield, higher price); SELL hits the bid.
            double signedHalf = side == OrderSide.BUY ? -half : half;
            double execYield = fairYield + (signedHalf + axe + noise) / 10_000.0;
            yields[i] = execYield;
            prices[i] = BondMath.cleanPriceFromYield(settlement, maturity, coupon, execYield);
        }
        int bestIdx = bestIndex(side, prices);

        List<DealerQuote> quotes = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            double spreadToCurve = (yields[i] - curveYield / 100.0) * 10_000.0;
            quotes.add(new DealerQuote(
                    DEALERS[i],
                    bd(prices[i], 4),
                    bd(yields[i] * 100.0, 4),
                    bd(spreadToCurve, 1),
                    quantity,
                    i == bestIdx));
        }
        return new QuoteSet(bd(tenor, 2), bd(curveYield, 4), bd(creditBps, 1),
                bd(fairYield * 100.0, 4), bd(fairClean, 4), quotes);
    }

    /** BUY takes the lowest offer; SELL takes the highest bid. */
    private static int bestIndex(OrderSide side, double[] prices) {
        int best = 0;
        for (int i = 1; i < prices.length; i++) {
            boolean better = side == OrderSide.BUY ? prices[i] < prices[best] : prices[i] > prices[best];
            if (better) {
                best = i;
            }
        }
        return best;
    }

    /** Bid/offer widens with lower credit quality and larger size. */
    private static double halfSpreadBps(double creditBps, double notional) {
        double base = Math.max(2.0, Math.min(creditBps * 0.03, 25.0));
        double sizeFactor = 1.0 + Math.min(notional / 10_000_000.0, 3.0) * 0.4;
        return base * sizeFactor;
    }

    private static double uniform(Random rng, double lo, double hi) {
        return lo + rng.nextDouble() * (hi - lo);
    }

    private static BigDecimal bd(double v, int scale) {
        return BigDecimal.valueOf(v).setScale(scale, RoundingMode.HALF_UP);
    }
}
