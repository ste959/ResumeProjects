package com.bonddesk.rates;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

/**
 * A live panel of dealers making OTC markets by request-for-quote — the fixed-income analogue of the
 * exchange's market maker + order flow. Each RFQ is shopped to {@code n} dealers who quote off the
 * curve with their own spread and inventory skew; the client takes best execution. Two real effects
 * are modelled, which together create the classic RFQ dilemma:
 *
 * <ul>
 *   <li><b>Competition</b> — more dealers means more quotes to pick the best from (tighter execution).</li>
 *   <li><b>Information leakage</b> — but shopping the order more widely leaks the client's intent, so
 *       the reference mid moves against them by {@code λ·size·ln(1+n)}. Past a point, leakage outweighs
 *       competition — there is an optimal number of dealers to show.</li>
 * </ul>
 *
 * Dealer inventories evolve as they win trades, feeding back into their skews. Not thread-safe.
 */
public final class DealerMarket {

    private static final String[] NAMES =
            {"Goldman", "JPMorgan", "MorganStanley", "Citi", "BofA", "Barclays", "Deutsche", "Nomura"};

    private final List<Dealer> dealers = new ArrayList<>();
    private final double leakageLambda;
    private final Random rng;

    public DealerMarket(long seed) {
        this.rng = new Random(seed);
        this.leakageLambda = 0.006;                        // price points per $mm per ln(1+n)
        for (int i = 0; i < NAMES.length; i++) {
            if (i == 0) {
                // Dealer 0 is "our desk" — a competitive, flat-started market maker so it wins a
                // healthy share of the flow and actually builds a book to risk-manage.
                dealers.add(new Dealer(NAMES[i], 0.08, 0.005, 0));
            } else {
                double half = 0.05 + rng.nextDouble() * 0.10;   // 5–15¢ base half-spread per 100
                double skew = 0.003 + rng.nextDouble() * 0.004; // shaded per $mm inventory
                double inv0 = (rng.nextDouble() * 2 - 1) * 8;   // ±8mm starting axe
                dealers.add(new Dealer(NAMES[i], half, skew, inv0));
            }
        }
    }

    public int dealerCount() {
        return dealers.size();
    }

    public List<Dealer> dealers() {
        return dealers;
    }

    /** Run one RFQ auction: shop to {@code nDealers}, take best-ex, book with the winner, return the TCA. */
    public RfqAuction runAuction(String instrument, Bond bond, RateCurve curve, double marketSpreadBps,
                                 boolean clientBuys, double sizeMM, int nDealers) {
        double mid = BondMath.price(bond, curve, marketSpreadBps);
        double dv01 = BondMath.dv01(bond, curve, marketSpreadBps);
        int n = Math.max(1, Math.min(nDealers, dealers.size()));
        double sideSign = clientBuys ? 1 : -1;

        double leakage = leakageLambda * sizeMM * Math.log(1 + n);
        double midAdj = mid + sideSign * leakage;          // effective mid moves against the client
        double competitionShade = 0.006 * (n - 1);         // dealers widen a touch when they know they compete

        // Dealer 0 ("our desk") is always on the panel; the rest of the n are a random subset.
        List<Integer> others = new ArrayList<>();
        for (int i = 1; i < dealers.size(); i++) others.add(i);
        Collections.shuffle(others, rng);
        List<Integer> pool = new ArrayList<>();
        pool.add(0);
        for (int k = 0; k < n - 1 && k < others.size(); k++) pool.add(others.get(k));

        int winnerPos = 0;
        double bestPrice = 0, second = Double.NaN;
        double[] px = new double[n];
        for (int k = 0; k < n; k++) {
            px[k] = dealers.get(pool.get(k)).quote(clientBuys, midAdj, competitionShade);
            if (k == 0 || (clientBuys ? px[k] < bestPrice : px[k] > bestPrice)) {
                bestPrice = px[k];
                winnerPos = k;
            }
        }
        for (int k = 0; k < n; k++) {
            if (k == winnerPos) continue;
            if (Double.isNaN(second) || (clientBuys ? px[k] < second : px[k] > second)) second = px[k];
        }

        List<RfqAuction.Quote> quotes = new ArrayList<>();
        for (int k = 0; k < n; k++) {
            int di = pool.get(k);
            double fromMidBps = dv01 > 0 ? (px[k] - mid) * sideSign / dv01 : 0;
            quotes.add(new RfqAuction.Quote(di, dealers.get(di).name(), round(px[k], 4), round(fromMidBps, 2), k == winnerPos));
        }

        double costPx = (bestPrice - mid) * sideSign;
        double competition = Double.isNaN(second) ? 0 : Math.abs(second - bestPrice);
        dealers.get(pool.get(winnerPos)).onWin(clientBuys, sizeMM);   // book with the winner

        return new RfqAuction(instrument, clientBuys, sizeMM, round(mid, 4), round(leakage, 4), quotes,
                winnerPos, round(bestPrice, 4), round(costPx, 4), round(dv01 > 0 ? costPx / dv01 : 0, 3),
                round(competition, 4));
    }

    private static double round(double v, int dp) {
        double f = Math.pow(10, dp);
        return Math.round(v * f) / f;
    }
}
