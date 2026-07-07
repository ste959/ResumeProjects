package com.bonddesk.exchange;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;

/**
 * The microstructure analytics only owning the matching engine makes possible: it logs every market-
 * maker fill with the market context at the time, then <b>marks each out</b> over a fixed horizon to
 * split the maker's edge into <b>spread capture</b> (what it earned versus mid at the trade) and
 * <b>adverse selection</b> (how far the mid then moved against it — the informed-flow tax). Fills are
 * tagged by aggressor type (informed / noise / you) so the adverse selection can be attributed.
 *
 * <p>Listens on the engine after the maker (so it reads the post-fill inventory). Not thread-safe.
 */
public final class MakerAnalytics implements ExchangeListener {

    public static final int HORIZON = 20;   // ticks (~2s at 10 Hz) over which to mark out a fill

    /** One maker fill with its context; markout/adverse are stamped HORIZON ticks later. */
    public static final class Fill {
        public final long seq, tick, priceTicks, sizeLots, mid0Ticks, spreadTicks, invAfterLots;
        public final boolean mmBought;
        public final char aggr;             // I=informed, N=noise, Y=you, ?=other
        public final double edgeTicks;      // spread captured vs mid at fill (signed, +=good)
        public Double adverseTicks;         // price impact after HORIZON (signed, −=adverse selection)
        public Double markoutTicks;         // edge + adverse = the fill's realised markout

        Fill(long seq, long tick, boolean mmBought, long priceTicks, long sizeLots, long mid0Ticks,
             long spreadTicks, long invAfterLots, char aggr, double edgeTicks) {
            this.seq = seq; this.tick = tick; this.mmBought = mmBought; this.priceTicks = priceTicks;
            this.sizeLots = sizeLots; this.mid0Ticks = mid0Ticks; this.spreadTicks = spreadTicks;
            this.invAfterLots = invAfterLots; this.aggr = aggr; this.edgeTicks = edgeTicks;
        }
    }

    private final MarketMaker mm;
    private final Deque<Fill> fills = new ArrayDeque<>();   // newest first, bounded
    private long curTick, curMid, curSpread;
    private long fillCount, adverseCount, informedFills, markedOut;
    private double sumEdgeTickLots, sumAdverseTickLots;

    public MakerAnalytics(MarketMaker mm) {
        this.mm = mm;
    }

    /** Called at the start of each tick: sets the reference mid for fills and marks out matured fills. */
    public void beginTick(long tick, long midTicks, long spreadTicks) {
        curTick = tick;
        curMid = midTicks;
        curSpread = spreadTicks;
        synchronized (fills) {
            for (Fill f : fills) {
                if (f.markoutTicks == null && tick - f.tick >= HORIZON && f.mid0Ticks > 0) {
                    long mmSide = f.mmBought ? 1 : -1;
                    double adverse = mmSide * (midTicks - f.mid0Ticks);   // mid drift after the fill
                    f.adverseTicks = adverse;
                    f.markoutTicks = f.edgeTicks + adverse;
                    sumAdverseTickLots += adverse * f.sizeLots;
                    markedOut++;
                    if (adverse < 0) adverseCount++;
                }
            }
        }
    }

    @Override
    public void onTrade(Trade t) {
        if (!MarketMaker.ID.equals(t.makerParticipant())) {
            return;
        }
        boolean mmBought = t.aggressorSide() == Side.SELL;      // taker sold → maker bought
        long mmSide = mmBought ? 1 : -1;
        double edge = mmSide * (curMid - t.priceTicks());       // captured spread vs mid at the fill
        char aggr = classify(t.takerParticipant());
        Fill f = new Fill(t.seq(), curTick, mmBought, t.priceTicks(), t.qty(), curMid, curSpread,
                mm.inventory(), aggr, edge);
        synchronized (fills) {
            fills.addFirst(f);
            while (fills.size() > 400) fills.removeLast();
        }
        fillCount++;
        sumEdgeTickLots += edge * t.qty();
        if (aggr == 'I') informedFills++;
    }

    private static char classify(String p) {
        if (p.startsWith("INF")) return 'I';
        if (p.startsWith("NSE")) return 'N';
        if (p.equals("YOU")) return 'Y';
        return '?';
    }

    public List<Fill> recentFills(int n) {
        synchronized (fills) {
            List<Fill> out = new ArrayList<>(fills);
            return out.size() > n ? out.subList(0, n) : out;
        }
    }

    public long fillCount() { return fillCount; }
    public long adverseCount() { return adverseCount; }
    public long informedFills() { return informedFills; }
    public long markedOut() { return markedOut; }
    public double sumEdgeTickLots() { return sumEdgeTickLots; }
    public double sumAdverseTickLots() { return sumAdverseTickLots; }
}
