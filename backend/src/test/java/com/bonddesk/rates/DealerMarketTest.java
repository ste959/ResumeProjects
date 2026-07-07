package com.bonddesk.rates;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/** The dealer market: inventory skew, best execution, booking, and the leakage trade-off. */
class DealerMarketTest {

    private static final double[] TENORS = {0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30};
    private static final double[] PAR = {4.35, 4.20, 4.00, 3.80, 3.75, 3.85, 4.00, 4.20, 4.55, 4.50};
    private final RateCurve curve = CurveBootstrap.fromPar(TENORS, PAR);
    private final Bond bond = new Bond(4.0, 10.0, 2, 100.0);

    @Test
    void inventorySkewShadesTheWholeMarketDownWhenLong() {
        Dealer flat = new Dealer("D", 0.10, 0.01, 0);
        Dealer longD = new Dealer("D", 0.10, 0.01, 20);   // 20mm long → wants to sell
        // Long dealer offers cheaper (keener to sell) and bids lower (reluctant to buy).
        assertThat(longD.quote(true, 100, 0)).isLessThan(flat.quote(true, 100, 0));
        assertThat(longD.quote(false, 100, 0)).isLessThan(flat.quote(false, 100, 0));
    }

    @Test
    void bestExecutionPicksTheBestQuote() {
        DealerMarket m = new DealerMarket(1);
        RfqAuction a = m.runAuction("T 4 10y", bond, curve, 30, true, 5, 6);   // client buys
        double bestOfferedPrice = a.quotes().stream().mapToDouble(RfqAuction.Quote::price).min().orElseThrow();
        assertThat(a.executedPrice()).isEqualTo(bestOfferedPrice);             // buyer takes the lowest offer
        assertThat(a.winner().best()).isTrue();
    }

    @Test
    void winningDealerBooksTheTrade() {
        DealerMarket m = new DealerMarket(2);
        double[] before = m.dealers().stream().mapToDouble(Dealer::inventory).toArray();
        RfqAuction a = m.runAuction("T", bond, curve, 30, true, 5, 6);   // client buys 5mm
        int winnerDealer = a.winner().dealer();
        // client bought → the winning dealer sold → its inventory fell by 5mm
        assertThat(m.dealers().get(winnerDealer).inventory())
                .isCloseTo(before[winnerDealer] - 5, org.assertj.core.data.Offset.offset(1e-9));
    }

    @Test
    void leakageRisesWithTheNumberOfDealersShopped() {
        DealerMarket m = new DealerMarket(3);
        double leakSmall = m.runAuction("T", bond, curve, 30, true, 10, 2).leakagePx();
        double leakWide = m.runAuction("T", bond, curve, 30, true, 10, 8).leakagePx();
        assertThat(leakWide).isGreaterThan(leakSmall);
    }

    @Test
    void clientPaysTheSpreadOnEntry() {
        DealerMarket m = new DealerMarket(4);
        RfqAuction a = m.runAuction("T", bond, curve, 30, true, 5, 5);
        assertThat(a.costPx()).isGreaterThan(0);           // executed above the composite mid on a buy
        assertThat(a.costBps()).isGreaterThan(0);
    }
}
