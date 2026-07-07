package com.bonddesk.oms.rates;

import com.bonddesk.oms.fixedincome.YieldCurve;
import com.bonddesk.oms.fixedincome.YieldCurveService;
import com.bonddesk.oms.rates.RatesDtos.AnalyticsView;
import com.bonddesk.oms.rates.RatesDtos.BookView;
import com.bonddesk.oms.rates.RatesDtos.CostBySize;
import com.bonddesk.oms.rates.RatesDtos.CurveView;
import com.bonddesk.oms.rates.RatesDtos.DealerView;
import com.bonddesk.oms.rates.RatesDtos.KrView;
import com.bonddesk.oms.rates.RatesDtos.LeakagePoint;
import com.bonddesk.oms.rates.RatesDtos.PnlAttribution;
import com.bonddesk.oms.rates.RatesDtos.PositionView;
import com.bonddesk.oms.rates.RatesDtos.QuoteView;
import com.bonddesk.oms.rates.RatesDtos.RfqView;
import com.bonddesk.oms.rates.RatesDtos.ShockRequest;
import com.bonddesk.oms.rates.RatesDtos.Snapshot;
import com.bonddesk.oms.rates.RatesDtos.SubmitRfqRequest;
import com.bonddesk.rates.Bond;
import com.bonddesk.rates.BondMath;
import com.bonddesk.rates.CurveBootstrap;
import com.bonddesk.rates.Dealer;
import com.bonddesk.rates.DealerMarket;
import com.bonddesk.rates.RateCurve;
import com.bonddesk.rates.RatesBook;
import com.bonddesk.rates.RfqAuction;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.locks.ReentrantLock;

/**
 * The live rates dealing desk: our matching-engine-grade rates engine ({@code com.bonddesk.rates})
 * driven by a real, evolving Treasury curve and a stream of client RFQs shopped across a dealer panel.
 * We are one dealer; we win some flow, accumulate a book, and attribute the desk's P&L to its drivers
 * (trading spread · carry · curve moves · credit spread) while measuring the RFQ market's
 * transaction-cost microstructure. A lock serialises the tick loop with user RFQ/shock requests.
 */
@Service
public class RatesSimulation {

    private final YieldCurveService curveService;
    private final ObjectMapper mapper;
    private final RatesSocketHandler socket;

    private final ReentrantLock lock = new ReentrantLock();
    private final Random rng = new Random(9);
    private final DealerMarket market = new DealerMarket(9);
    private final RatesBook book = new RatesBook();
    private final Map<String, Bond> bonds = new LinkedHashMap<>();
    private final Map<String, Double> baseSpreads = new LinkedHashMap<>();
    private final Map<String, Double> spreads = new LinkedHashMap<>();
    private final List<String> universe = new ArrayList<>();

    private RateCurve curve;
    private RateCurve prevCurve;
    private Map<String, Double> prevSpreads;
    private double shockParallelBps, shockSlopeBps, noiseParallel, noiseSlope;

    // cumulative P&L attribution ($)
    private double pnlTrading, pnlCarry, pnlRateParallel, pnlRateReshape, pnlCredit;
    // RFQ analytics
    private long totalRfqs, ourWins;
    private double sumCostBps;
    private final double[] leakSum = new double[9], leakCost = new double[9];
    private final long[] leakCount = new long[9];
    private final double[] sizeCost = new double[3];
    private final long[] sizeCount = new long[3];

    private long tick;
    private volatile RfqAuction lastAuction;
    private volatile Snapshot latest;

    public RatesSimulation(YieldCurveService curveService, ObjectMapper mapper, RatesSocketHandler socket) {
        this.curveService = curveService;
        this.mapper = mapper;
        this.socket = socket;
        addBond("UST 2Y", 3.75, 2, 3);
        addBond("UST 5Y", 3.90, 5, 4);
        addBond("UST 10Y", 4.20, 10, 5);
        addBond("UST 30Y", 4.50, 30, 6);
        addBond("AAPL 4⅝ '30", 4.625, 5, 55);
        addBond("F 6.1 '32", 6.10, 7, 175);
    }

    private void addBond(String id, double coupon, double maturity, double spreadBps) {
        bonds.put(id, Bond.of(coupon, maturity));
        baseSpreads.put(id, spreadBps);
        spreads.put(id, spreadBps);
        universe.add(id);
    }

    @PostConstruct
    void init() {
        rebuildCurve();
        prevCurve = curve;
        prevSpreads = new LinkedHashMap<>(spreads);
        latest = buildSnapshot();
    }

    @Scheduled(fixedDelay = 700)
    public void tick() {
        Snapshot snap;
        lock.lock();
        try {
            tick++;
            evolve();
            attribute();                       // mark the existing book over the move
            RfqAuction a = randomRfq();        // one client RFQ, shopped to the panel
            recordRfq(a, true);
            prevCurve = curve;
            prevSpreads = new LinkedHashMap<>(spreads);
            snap = buildSnapshot();
        } finally {
            lock.unlock();
        }
        latest = snap;
        try {
            socket.broadcast(mapper.writeValueAsString(snap));
        } catch (Exception ignored) {
        }
    }

    // ── evolution ────────────────────────────────────────────────────────────────────────────────
    private void rebuildCurve() {
        YieldCurve par = curveService.current();
        RateCurve base = CurveBootstrap.fromPar(par.tenors(), par.yields());
        curve = applyShock(base, shockParallelBps + noiseParallel, shockSlopeBps + noiseSlope);
    }

    private void evolve() {
        noiseParallel = 0.97 * noiseParallel + rng.nextGaussian() * 0.4;   // mean-reverting rate noise
        noiseSlope = 0.97 * noiseSlope + rng.nextGaussian() * 0.3;
        rebuildCurve();
        for (String id : universe) {                                       // spreads drift back to base
            double s = spreads.get(id) + rng.nextGaussian() * 0.5 + 0.05 * (baseSpreads.get(id) - spreads.get(id));
            spreads.put(id, Math.max(0, s));
        }
    }

    private static RateCurve applyShock(RateCurve base, double parallelBps, double slopeBps) {
        double[] t = base.tenors(), z = base.zeros(), nz = new double[z.length];
        for (int i = 0; i < z.length; i++) {
            nz[i] = z[i] + parallelBps / 1e4 + slopeBps / 1e4 * ((t[i] - 5.0) / 25.0);  // pivot at 5y
        }
        return new RateCurve(t, nz);
    }

    // ── P&L attribution over the last move ──────────────────────────────────────────────────────
    private void attribute() {
        double curvePnl = book.valueUsd(bonds, curve, prevSpreads) - book.valueUsd(bonds, prevCurve, prevSpreads);
        double creditPnl = book.valueUsd(bonds, curve, spreads) - book.valueUsd(bonds, curve, prevSpreads);
        double[] z0 = prevCurve.zeros(), z1 = curve.zeros();
        double meanDzBps = 0;
        for (int i = 0; i < z0.length; i++) meanDzBps += (z1[i] - z0[i]) * 1e4;
        meanDzBps /= z0.length;
        double parallelPnl = -book.dv01Usd(bonds, prevCurve, prevSpreads) * meanDzBps;
        double dt = 1.0 / 252;
        double carryTick = 0;
        for (var e : book.positions().entrySet()) {
            Bond b = bonds.get(e.getKey());
            if (b != null) carryTick += e.getValue() * 1e6 * (b.couponPct() / 100.0) * dt;
        }
        pnlRateParallel += parallelPnl;
        pnlRateReshape += curvePnl - parallelPnl;
        pnlCredit += creditPnl;
        pnlCarry += carryTick;
    }

    // ── RFQ auctions ─────────────────────────────────────────────────────────────────────────────
    private RfqAuction randomRfq() {
        String id = universe.get(rng.nextInt(universe.size()));
        boolean buys = rng.nextBoolean();
        double size = 1 + rng.nextInt(25);
        int n = 2 + rng.nextInt(7);
        return market.runAuction(id, bonds.get(id), curve, spreads.get(id), buys, size, n);
    }

    private void recordRfq(RfqAuction a, boolean book_) {
        lastAuction = a;
        totalRfqs++;
        sumCostBps += a.costBps();
        int n = a.quotes().size();
        if (n < leakSum.length) {
            leakSum[n] += a.leakagePx();
            leakCost[n] += a.costBps();
            leakCount[n]++;
        }
        int bucket = a.sizeMM() < 5 ? 0 : a.sizeMM() < 15 ? 1 : 2;
        sizeCost[bucket] += a.costBps();
        sizeCount[bucket]++;
        boolean weWon = a.winner().dealer() == 0;
        if (weWon) {
            ourWins++;
            if (book_) {
                pnlTrading += a.costPx() * a.sizeMM() * 1e4;     // we captured the spread the client paid
                book.trade(a.instrument(), a.clientBuys(), a.sizeMM());
            }
        }
    }

    // ── user actions ────────────────────────────────────────────────────────────────────────────
    public RfqView submitRfq(SubmitRfqRequest req) {
        lock.lock();
        try {
            String id = req.instrument() != null && bonds.containsKey(req.instrument()) ? req.instrument() : universe.get(0);
            boolean buys = !"SELL".equalsIgnoreCase(req.side());
            double size = req.sizeMM() == null ? 5 : req.sizeMM();
            int n = req.nDealers() == null ? 5 : Math.max(1, req.nDealers());
            RfqAuction a = market.runAuction(id, bonds.get(id), curve, spreads.get(id), buys, size, n);
            recordRfq(a, true);
            return rfqView(a);
        } finally {
            lock.unlock();
        }
    }

    public Snapshot shock(ShockRequest req) {
        lock.lock();
        try {
            shockParallelBps = req.parallelBps();
            shockSlopeBps = req.slopeBps();
            rebuildCurve();
            latest = buildSnapshot();
            return latest;
        } finally {
            lock.unlock();
        }
    }

    public Snapshot snapshot() {
        return latest != null ? latest : buildSnapshot();
    }

    // ── snapshot ────────────────────────────────────────────────────────────────────────────────
    private Snapshot buildSnapshot() {
        return new Snapshot(tick, curveView(), lastAuction == null ? null : rfqView(lastAuction),
                dealerViews(), bookView(), analyticsView());
    }

    private CurveView curveView() {
        YieldCurve par = curveService.current();
        double[] t = curve.tenors(), z = curve.zeros(), zr = new double[z.length];
        for (int i = 0; i < z.length; i++) zr[i] = round(z[i] * 100, 3);
        double[] pv = new double[t.length];
        for (int i = 0; i < t.length; i++) pv[i] = round(par.interpolate(t[i]), 3);
        return new CurveView(par.asOf().toString(), t, pv, zr, round(shockParallelBps + noiseParallel, 1), round(shockSlopeBps + noiseSlope, 1));
    }

    private RfqView rfqView(RfqAuction a) {
        List<QuoteView> qs = new ArrayList<>();
        for (RfqAuction.Quote q : a.quotes()) {
            boolean us = q.dealer() == 0;
            qs.add(new QuoteView(us ? "Our Desk" : q.name(), q.price(), q.fromMidBps(), q.best(), us));
        }
        boolean weWon = a.winner().dealer() == 0;
        return new RfqView(a.instrument(), a.clientBuys() ? "BUY" : "SELL", a.sizeMM(), a.quotes().size(),
                a.compositeMid(), a.leakagePx(), a.executedPrice(), weWon ? "Our Desk" : a.winner().name(),
                weWon, a.costBps(), a.competitionPx(), qs);
    }

    private List<DealerView> dealerViews() {
        List<DealerView> out = new ArrayList<>();
        List<Dealer> ds = market.dealers();
        for (int i = 0; i < ds.size(); i++) {
            out.add(new DealerView(i == 0 ? "Our Desk" : ds.get(i).name(), round(ds.get(i).inventory(), 1), i == 0));
        }
        return out;
    }

    private BookView bookView() {
        double value = book.valueUsd(bonds, curve, spreads);
        double dv01 = book.dv01Usd(bonds, curve, spreads);
        double[] kr = book.keyRateDv01Usd(bonds, curve, spreads);
        double[] t = curve.tenors();
        List<KrView> krv = new ArrayList<>();
        for (int i = 0; i < kr.length; i++) if (Math.abs(kr[i]) > 1) krv.add(new KrView(t[i], round(kr[i], 0)));
        List<PositionView> pos = new ArrayList<>();
        for (var e : book.positions().entrySet()) {
            if (Math.abs(e.getValue()) < 0.01) continue;
            Bond b = bonds.get(e.getKey());
            pos.add(new PositionView(e.getKey(), round(e.getValue(), 1),
                    round(BondMath.price(b, curve, spreads.get(e.getKey())), 3),
                    round(e.getValue() * BondMath.dv01(b, curve, spreads.get(e.getKey())) * 1e4, 0)));
        }
        double total = pnlTrading + pnlCarry + pnlRateParallel + pnlRateReshape + pnlCredit;
        PnlAttribution pnl = new PnlAttribution(round(total, 0), round(pnlTrading, 0), round(pnlCarry, 0),
                round(pnlRateParallel, 0), round(pnlRateReshape, 0), round(pnlCredit, 0));
        return new BookView(round(value, 0), round(dv01, 0), krv, pos, pnl);
    }

    private AnalyticsView analyticsView() {
        List<LeakagePoint> leak = new ArrayList<>();
        for (int n = 2; n < leakSum.length; n++) {
            if (leakCount[n] > 0) {
                leak.add(new LeakagePoint(n, round(leakSum[n] / leakCount[n], 4), round(leakCost[n] / leakCount[n], 2), leakCount[n]));
            }
        }
        String[] labels = {"< $5mm", "$5–15mm", "> $15mm"};
        List<CostBySize> cbs = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            if (sizeCount[i] > 0) cbs.add(new CostBySize(labels[i], round(sizeCost[i] / sizeCount[i], 2), sizeCount[i]));
        }
        return new AnalyticsView(round(totalRfqs > 0 ? 100.0 * ourWins / totalRfqs : 0, 1), ourWins, totalRfqs,
                round(totalRfqs > 0 ? sumCostBps / totalRfqs : 0, 2), leak, cbs);
    }

    private static double round(double v, int dp) {
        double f = Math.pow(10, dp);
        return Math.round(v * f) / f;
    }
}
