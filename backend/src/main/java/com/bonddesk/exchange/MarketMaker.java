package com.bonddesk.exchange;

/**
 * An inventory-skewed market maker that quotes into the engine — the Avellaneda–Stoikov idea in
 * integer tick space: centre a two-sided quote on a <b>reservation price</b> that leans against the
 * current inventory (quote lower when long, higher when short, to mean-revert the position), around
 * a base half-spread. Post-only, so it is always the maker and never crosses.
 *
 * <p>It listens to the engine so it sees its own fills the instant an aggressor lifts a quote, and
 * marks inventory + cash from them — the raw material for P&L attribution (spread capture vs.
 * adverse selection vs. inventory) computed downstream. Not thread-safe; driven on the engine thread.
 */
public final class MarketMaker implements ExchangeListener {

    public static final String ID = "MM";

    private final long baseHalfSpread;   // ticks
    private final long invSkew;          // ticks of quote shift per lot of inventory
    private final long quoteSize;        // lots per quote
    private final long maxInventory;     // stop adding to a side beyond this

    private long inventory;              // net lots (long > 0, short < 0)
    private long cash;                   // in tick·lots; +ve = received
    private long bidId, askId;
    private long fills;

    public MarketMaker(long baseHalfSpread, long invSkew, long quoteSize, long maxInventory) {
        this.baseHalfSpread = baseHalfSpread;
        this.invSkew = invSkew;
        this.quoteSize = quoteSize;
        this.maxInventory = maxInventory;
    }

    /** Cancel stale quotes and repost a fresh two-sided quote around the inventory-skewed reservation. */
    public void requote(OrderBook book, long fairTicks) {
        if (bidId > 0) book.cancel(bidId);
        if (askId > 0) book.cancel(askId);
        bidId = askId = 0;

        long reservation = fairTicks - inventory * invSkew;   // lean against inventory
        long bidPx = reservation - baseHalfSpread;
        long askPx = reservation + baseHalfSpread;

        if (inventory < maxInventory && bidPx > 0) {
            SubmitResult r = book.submit(ID, Side.BUY, OrderType.LIMIT, TimeInForce.GTC, true, bidPx, quoteSize);
            if (r.accepted()) bidId = r.orderId();            // rejected only if it would cross (post-only)
        }
        if (inventory > -maxInventory) {
            SubmitResult r = book.submit(ID, Side.SELL, OrderType.LIMIT, TimeInForce.GTC, true, askPx, quoteSize);
            if (r.accepted()) askId = r.orderId();
        }
    }

    @Override
    public void onTrade(Trade t) {
        if (!ID.equals(t.makerParticipant())) {
            return;                                           // MM only ever rests (post-only) → always maker
        }
        long notional = t.priceTicks() * t.qty();
        if (t.aggressorSide() == Side.BUY) {                  // taker bought → MM (maker) sold
            inventory -= t.qty();
            cash += notional;
        } else {                                              // taker sold → MM bought
            inventory += t.qty();
            cash -= notional;
        }
        fills++;
    }

    public long inventory() { return inventory; }
    public long cash() { return cash; }
    public long fills() { return fills; }

    /** Mark-to-market P&L in tick·lots at the given mark price. */
    public long pnl(long markTicks) {
        return cash + inventory * markTicks;
    }
}
