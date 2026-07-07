package com.bonddesk.rates;

/**
 * One dealer on the RFQ panel. It quotes around an (already leakage-adjusted) mid with its own
 * base half-spread, and <b>skews the whole market by its inventory</b>: a dealer that is long wants
 * to sell, so it lowers both its offer (keener to sell) and its bid (reluctant to buy more) — the
 * fixed-income analogue of the exchange market maker's inventory skew. Winning a trade moves its
 * inventory, which feeds back into the next quote.
 */
public final class Dealer {

    private final String name;
    private final double baseHalfSpread;   // price points per 100
    private final double invSkew;          // price points shaded per $mm of inventory
    private double inventory;              // $mm face, signed (+ long)

    public Dealer(String name, double baseHalfSpread, double invSkew, double inventory0) {
        this.name = name;
        this.baseHalfSpread = baseHalfSpread;
        this.invSkew = invSkew;
        this.inventory = inventory0;
    }

    /** Quote a price for a client {@code BUY} (dealer offers) or {@code SELL} (dealer bids). */
    public double quote(boolean clientBuys, double midAdj, double competitionShade) {
        double half = baseHalfSpread + competitionShade;
        double skew = invSkew * inventory;                 // long → shade the whole market down
        return clientBuys ? midAdj + half - skew : midAdj - half - skew;
    }

    public void onWin(boolean clientBuys, double sizeMM) {
        inventory += clientBuys ? -sizeMM : sizeMM;        // dealer sells on a client buy, buys on a sell
    }

    public String name() { return name; }
    public double inventory() { return inventory; }
    public double baseHalfSpread() { return baseHalfSpread; }
}
