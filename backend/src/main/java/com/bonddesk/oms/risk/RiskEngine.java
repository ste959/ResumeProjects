package com.bonddesk.oms.risk;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.pricing.BondMath;
import com.bonddesk.oms.risk.dto.RiskDtos.PortfolioRiskReport;
import com.bonddesk.oms.risk.dto.RiskDtos.ScenarioPnl;
import com.bonddesk.oms.service.PositionService;
import com.bonddesk.oms.util.Pricing;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Aggregate portfolio risk across asset classes — the risk you actually run is aggregate and
 * by factor, not a list of line items. Reuses the bond math for interest-rate risk (DV01),
 * expresses a parametric 1-day 95% VaR (diversified vs. undiversified so the diversification
 * benefit is explicit), and stresses the book against scenarios, including a correlated
 * risk-off shock where rates, equities and credit move together (the tail that hurts most).
 */
@Service
public class RiskEngine {

    // Representative daily factor volatilities and the 95% one-tailed z-score.
    private static final double RATE_VOL_BP = 7.0;      // bp/day
    private static final double EQUITY_VOL = 0.012;     // 1.2%/day
    private static final double CREDIT_VOL_BP = 3.0;    // bp/day of spread
    private static final double Z95 = 1.645;

    private final PositionService positions;
    private final Clock clock;

    public RiskEngine(PositionService positions, Clock clock) {
        this.positions = positions;
        this.clock = clock;
    }

    public PortfolioRiskReport compute(String portfolio) {
        List<Position> book = positions.forPortfolio(portfolio);
        LocalDate settle = LocalDate.ofInstant(clock.instant(), ZoneOffset.UTC);

        double aggDv01 = 0;
        double corpDv01 = 0;
        double fiNet = 0;
        double eqNet = 0;
        double gross = 0;
        int n = 0;
        Map<String, Double> sector = new TreeMap<>();

        for (Position p : book) {
            Security s = p.getSecurity();
            BigDecimal netQty = p.getNetQuantity();
            if (netQty == null || netQty.signum() == 0) {
                continue;
            }
            n++;
            double notional = Pricing.notional(s, netQty, s.getCleanPrice()).doubleValue();
            gross += Math.abs(notional);
            sector.merge(s.getSector() == null ? "UNKNOWN" : s.getSector(), notional, Double::sum);

            boolean pricableBond = s.getAssetClass() == AssetClass.FIXED_INCOME
                    && s.getMaturityDate() != null && s.getMaturityDate().isAfter(settle)
                    && s.getCouponRate() != null;
            if (pricableBond) {
                double coupon = s.getCouponRate().doubleValue() / 100.0;
                double dv01Per100 = BondMath.analyze(settle, s.getMaturityDate(), coupon,
                        s.getCleanPrice().doubleValue()).dv01();
                double posDv01 = dv01Per100 * netQty.doubleValue() / 100.0; // signed by position
                aggDv01 += posDv01;
                if (!isSovereign(s)) {
                    corpDv01 += posDv01;
                }
                fiNet += notional;
            } else {
                eqNet += notional;
            }
        }

        double rateSigma = Math.abs(aggDv01) * RATE_VOL_BP;
        double eqSigma = Math.abs(eqNet) * EQUITY_VOL;
        double creditSigma = Math.abs(corpDv01) * CREDIT_VOL_BP;
        double undiversified = Z95 * (rateSigma + eqSigma + creditSigma);
        double diversified = Z95 * Math.sqrt(rateSigma * rateSigma + eqSigma * eqSigma + creditSigma * creditSigma);

        List<ScenarioPnl> scenarios = List.of(
                new ScenarioPnl("RATES_+100BP", round(-aggDv01 * 100), "parallel curve shift +100bp"),
                new ScenarioPnl("EQUITY_-10%", round(-eqNet * 0.10), "equities down 10%"),
                new ScenarioPnl("CREDIT_+50BP", round(-corpDv01 * 50), "corporate spreads widen 50bp"),
                new ScenarioPnl("RISK_OFF", round(aggDv01 * 30 - eqNet * 0.08 - corpDv01 * 75),
                        "flight to quality: rates -30bp, equities -8%, credit +75bp"));

        Map<String, Double> sectorRounded = new LinkedHashMap<>();
        sector.forEach((k, v) -> sectorRounded.put(k, round(v)));

        return new PortfolioRiskReport(portfolio, n, round(gross), round(fiNet + eqNet),
                round(fiNet), round(eqNet), round(aggDv01), round(corpDv01),
                round(diversified), round(undiversified), round(undiversified - diversified),
                sectorRounded, scenarios);
    }

    private static boolean isSovereign(Security s) {
        String sec = s.getSector();
        return sec != null && (sec.equalsIgnoreCase("SOVEREIGN") || sec.equalsIgnoreCase("TREASURY"));
    }

    private static double round(double v) {
        return Math.round(v * 100.0) / 100.0;
    }
}
