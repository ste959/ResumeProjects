package com.bonddesk.oms.tax;

import com.bonddesk.oms.exception.BadRequestException;
import com.bonddesk.oms.tax.dto.TaxDtos.Disposition;
import com.bonddesk.oms.tax.dto.TaxDtos.TaxReport;
import com.bonddesk.oms.tax.dto.TaxDtos.TaxRequest;
import com.bonddesk.oms.tax.dto.TaxDtos.TaxTrade;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Tax accounting for a sequence of trades — the most-overlooked cost in backtesting.
 *
 * <p>Models what actually determines the tax bill, not a flat percentage:
 * <ul>
 *   <li><b>Lot-level accounting</b> (FIFO / LIFO / HIFO), because which lots you sell changes
 *       the realized gain — average cost is wrong for tax.</li>
 *   <li><b>Holding period</b> — short-term (&le; 1 year, taxed at the ordinary rate) vs.
 *       long-term. High-turnover strategies are all short-term, so turnover has a tax cost.</li>
 *   <li><b>Wash sales</b> (§1091) for <b>securities</b>: a loss is disallowed if the same name
 *       is repurchased within 30 days. <b>Crypto is property</b>, so the rule does not apply —
 *       a real asymmetry between the asset classes.</li>
 *   <li><b>Regime</b>: retail capital-gains vs. <b>§475(f) trader mark-to-market</b> — the
 *       regime a prop firm actually elects (everything marked at period-end, all ordinary, no
 *       wash sales, no long-term).</li>
 * </ul>
 *
 * <p>Simplifications (documented deliberately): the disallowed wash-sale loss is recognised as
 * a current-period hit rather than carried into the replacement lot's basis; short sales are
 * not lot-matched; capital-loss netting/carryforward limits are not applied.
 */
@Service
public class TaxEngine {

    private static final long LONG_TERM_DAYS = 365;
    private static final int WASH_WINDOW_DAYS = 30;

    private static final class Lot {
        double qty;
        final double basis;
        final Instant acquired;

        Lot(double qty, double basis, Instant acquired) {
            this.qty = qty;
            this.basis = basis;
            this.acquired = acquired;
        }
    }

    private static final class Disp {
        Instant acquired;
        Instant sold;
        double qty;
        double proceeds;
        double basis;
        double gain;
        long days;
        boolean longTerm;
        double wash;
    }

    public TaxReport compute(TaxRequest req) {
        if (req.trades() == null || req.trades().isEmpty()) {
            throw new BadRequestException("trades are required");
        }
        String assetClass = upper(req.assetClass(), "CRYPTO");
        String lotMethod = upper(req.lotMethod(), "FIFO");
        String regime = upper(req.regime(), "RETAIL");
        double ordinaryRate = req.ordinaryRate() == null ? 0.37 : req.ordinaryRate();
        double ltRate = req.longTermRate() == null ? 0.20 : req.longTermRate();
        boolean mtm = regime.equals("TRADER_MTM") || regime.equals("MTM") || regime.equals("475F");
        boolean washApplies = !mtm && (assetClass.equals("EQUITY") || assetClass.equals("EQUITIES"));

        List<TaxTrade> trades = new ArrayList<>(req.trades());
        trades.sort(Comparator.comparing(TaxTrade::time));

        List<Lot> lots = new ArrayList<>();
        List<Disp> disps = new ArrayList<>();
        for (TaxTrade t : trades) {
            if ("BUY".equalsIgnoreCase(t.side())) {
                lots.add(new Lot(t.quantity(), t.price(), t.time()));
            } else {
                disposeSell(lots, disps, t, lotMethod);
            }
        }

        if (washApplies) {
            applyWashSales(disps, trades);
        }

        double proceeds = 0;
        double realized = 0;
        double st = 0;
        double lt = 0;
        double wash = 0;
        for (Disp d : disps) {
            proceeds += d.proceeds;
            realized += d.gain;
            wash += d.wash;
            double taxable = d.gain + d.wash; // wash adds back the disallowed loss
            if (d.longTerm && !mtm) {
                lt += taxable;
            } else {
                st += taxable;
            }
        }

        double openQty = 0;
        double openBasisTotal = 0;
        for (Lot l : lots) {
            openQty += l.qty;
            openBasisTotal += l.qty * l.basis;
        }
        double openAvgBasis = openQty > 1e-12 ? openBasisTotal / openQty : 0;

        double unrealizedMtm = 0;
        double taxableGain;
        double taxOwed;
        double preTax;
        if (mtm) {
            double mark = req.markPrice() != null ? req.markPrice()
                    : trades.get(trades.size() - 1).price();
            unrealizedMtm = mark * openQty - openBasisTotal; // mark open lots to market
            taxableGain = realized + unrealizedMtm;          // all ordinary
            taxOwed = taxableGain * ordinaryRate;
            st = taxableGain;
            lt = 0;
            wash = 0;
            preTax = realized + unrealizedMtm;
        } else {
            taxableGain = st + lt;
            taxOwed = st * ordinaryRate + lt * ltRate;
            preTax = realized;
        }
        double afterTax = preTax - taxOwed;
        double effRate = Math.abs(preTax) > 1e-9 ? taxOwed / preTax : 0;

        List<Disposition> dispViews = new ArrayList<>(disps.size());
        for (Disp d : disps) {
            dispViews.add(new Disposition(d.acquired, d.sold, round(d.qty, 8), round(d.proceeds, 2),
                    round(d.basis, 2), round(d.gain, 2), d.days, d.longTerm, round(d.wash, 2)));
        }

        return new TaxReport(assetClass, regime, lotMethod, round(proceeds, 2), round(realized, 2),
                round(st, 2), round(lt, 2), round(wash, 2), round(unrealizedMtm, 2), round(taxableGain, 2),
                round(taxOwed, 2), round(preTax, 2), round(afterTax, 2), round(effRate, 4),
                round(openQty, 8), round(openAvgBasis, 6), dispViews);
    }

    private void disposeSell(List<Lot> lots, List<Disp> disps, TaxTrade t, String lotMethod) {
        double remaining = t.quantity();
        while (remaining > 1e-12 && !lots.isEmpty()) {
            int idx = selectLot(lots, lotMethod);
            Lot lot = lots.get(idx);
            double q = Math.min(remaining, lot.qty);
            Disp d = new Disp();
            d.acquired = lot.acquired;
            d.sold = t.time();
            d.qty = q;
            d.proceeds = q * t.price();
            d.basis = q * lot.basis;
            d.gain = d.proceeds - d.basis;
            d.days = Duration.between(lot.acquired, t.time()).toDays();
            // Long-term is "held MORE THAN one year" — a calendar-anniversary test, not a
            // 365-day count (which misclassifies a one-year hold spanning a leap day).
            LocalDate acq = LocalDate.ofInstant(lot.acquired, ZoneOffset.UTC);
            LocalDate sold = LocalDate.ofInstant(t.time(), ZoneOffset.UTC);
            d.longTerm = sold.isAfter(acq.plusYears(1));
            disps.add(d);
            lot.qty -= q;
            remaining -= q;
            if (lot.qty <= 1e-12) {
                lots.remove(idx);
            }
        }
        // remaining > 0 → sold more than held (a short); not lot-matched in this model.
    }

    /**
     * A realized loss is disallowed to the extent it is matched by a <em>replacement</em>
     * purchase within ±30 days of the sale. Two things the naive version got wrong:
     * <ol>
     *   <li>The originating purchase of the shares being sold is NOT a replacement (else a
     *       plain buy→sell-at-a-loss within 30 days would be wrongly disallowed).</li>
     *   <li>Each replacement share can wash only ONE loss — replacement capacity is consumed
     *       across dispositions so a single rebuy can't disallow multiple losses.</li>
     * </ol>
     * Simplification retained: a replacement is not required to still be held at year-end,
     * and the disallowed loss is not carried into the replacement lot's basis (see design log).
     */
    private void applyWashSales(List<Disp> disps, List<TaxTrade> trades) {
        // Pool of candidate replacement purchases with consumable capacity: {epochMillis, qty}.
        List<double[]> replacements = new ArrayList<>();
        for (TaxTrade t : trades) {
            if ("BUY".equalsIgnoreCase(t.side())) {
                replacements.add(new double[]{t.time().toEpochMilli(), t.quantity()});
            }
        }
        long windowMs = WASH_WINDOW_DAYS * 86_400_000L;
        for (Disp d : disps) {
            if (d.gain >= 0) {
                continue;
            }
            long soldMs = d.sold.toEpochMilli();
            long acquiredMs = d.acquired.toEpochMilli();
            double need = d.qty;
            double disallowedQty = 0;
            for (double[] r : replacements) {
                if (need <= 1e-12) {
                    break;
                }
                if (r[1] <= 1e-12 || Math.abs(soldMs - (long) r[0]) > windowMs) {
                    continue;
                }
                if ((long) r[0] == acquiredMs) {
                    continue; // the sold lot's own purchase is not a replacement for its loss
                }
                double use = Math.min(need, r[1]);
                disallowedQty += use;
                r[1] -= use;   // consume — this replacement can't wash another loss too
                need -= use;
            }
            if (d.qty > 1e-12 && disallowedQty > 0) {
                d.wash = -d.gain * (disallowedQty / d.qty); // positive: the loss added back
            }
        }
    }

    private static int selectLot(List<Lot> lots, String method) {
        return switch (method) {
            case "LIFO" -> lots.size() - 1;
            case "HIFO" -> {
                int best = 0;
                for (int i = 1; i < lots.size(); i++) {
                    if (lots.get(i).basis > lots.get(best).basis) {
                        best = i;
                    }
                }
                yield best;
            }
            default -> 0; // FIFO
        };
    }

    private static String upper(String s, String def) {
        return s == null || s.isBlank() ? def : s.toUpperCase();
    }

    private static double round(double v, int dp) {
        double scale = Math.pow(10, dp);
        return Math.round(v * scale) / scale;
    }
}
