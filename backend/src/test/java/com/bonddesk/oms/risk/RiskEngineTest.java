package com.bonddesk.oms.risk;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.risk.dto.RiskDtos.PortfolioRiskReport;
import com.bonddesk.oms.risk.dto.RiskDtos.ScenarioPnl;
import com.bonddesk.oms.service.PositionService;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class RiskEngineTest {

    private static Position bondPosition(String qty) {
        Security bond = new Security();
        bond.setAssetClass(AssetClass.FIXED_INCOME);
        bond.setCusip("912828YK0");
        bond.setSector("SOVEREIGN");
        bond.setCouponRate(new BigDecimal("4.0000"));
        bond.setMaturityDate(LocalDate.of(2036, 1, 15));
        bond.setCleanPrice(new BigDecimal("100.0000"));
        Position p = new Position();
        p.setPortfolio("P");
        p.setSecurity(bond);
        p.setNetQuantity(new BigDecimal(qty));
        p.setAvgCost(new BigDecimal("100"));
        return p;
    }

    @Test
    void aggregatesDv01AndStressesTheBook() {
        PositionService ps = mock(PositionService.class);
        when(ps.forPortfolio("P")).thenReturn(List.of(bondPosition("1000000")));
        Clock clock = Clock.fixed(Instant.parse("2026-01-15T00:00:00Z"), ZoneOffset.UTC);

        PortfolioRiskReport r = new RiskEngine(ps, clock).compute("P");

        // A long 10y bond has positive DV01 and loses when rates rise.
        assertThat(r.aggregateDv01()).isGreaterThan(0.0);
        ScenarioPnl ratesUp = r.scenarios().stream()
                .filter(s -> s.scenario().equals("RATES_+100BP")).findFirst().orElseThrow();
        assertThat(ratesUp.pnl()).isLessThan(0.0);
        // Rate P&L should be roughly -DV01 * 100 (DV01 is reported rounded, so allow slack).
        assertThat(ratesUp.pnl()).isCloseTo(-r.aggregateDv01() * 100, org.assertj.core.api.Assertions.within(1.0));
        assertThat(r.var95Diversified()).isPositive();
    }

    @Test
    void shortBondFlipsTheSignOfRateRisk() {
        PositionService ps = mock(PositionService.class);
        when(ps.forPortfolio("P")).thenReturn(List.of(bondPosition("-1000000")));
        Clock clock = Clock.fixed(Instant.parse("2026-01-15T00:00:00Z"), ZoneOffset.UTC);

        PortfolioRiskReport r = new RiskEngine(ps, clock).compute("P");

        assertThat(r.aggregateDv01()).isLessThan(0.0); // short is negative DV01
        ScenarioPnl ratesUp = r.scenarios().stream()
                .filter(s -> s.scenario().equals("RATES_+100BP")).findFirst().orElseThrow();
        assertThat(ratesUp.pnl()).isGreaterThan(0.0); // a short bond gains when rates rise
    }

    private static Position equityPosition(String qty) {
        Security eq = new Security();
        eq.setAssetClass(AssetClass.EQUITY);
        eq.setCusip("037833100");
        eq.setTicker("AAPL");
        eq.setSector("TECHNOLOGY");
        eq.setCleanPrice(new BigDecimal("230.00"));
        Position p = new Position();
        p.setPortfolio("P");
        p.setSecurity(eq);
        p.setNetQuantity(new BigDecimal(qty));
        p.setAvgCost(new BigDecimal("230"));
        return p;
    }

    @Test
    void unpriceableBondStaysInFixedIncomeNotEquity() {
        // A bond with no coupon/maturity (e.g. a floater or bad data) is un-priceable. It must
        // stay in fixed income — NOT fall through to the equity bucket and take the equity shock.
        Security frn = new Security();
        frn.setAssetClass(AssetClass.FIXED_INCOME);
        frn.setCusip("FRN00000X");
        frn.setSector("CORPORATE");
        frn.setCleanPrice(new BigDecimal("100.0")); // no coupon, no maturity → un-priceable
        Position p = new Position();
        p.setPortfolio("P");
        p.setSecurity(frn);
        p.setNetQuantity(new BigDecimal("1000000"));
        p.setAvgCost(new BigDecimal("100"));

        PositionService ps = mock(PositionService.class);
        when(ps.forPortfolio("P")).thenReturn(List.of(p));
        Clock clock = Clock.fixed(Instant.parse("2026-01-15T00:00:00Z"), ZoneOffset.UTC);

        PortfolioRiskReport r = new RiskEngine(ps, clock).compute("P");

        assertThat(r.fixedIncomeNotional()).isNotEqualTo(0.0);
        assertThat(r.equityNotional()).isEqualTo(0.0); // NOT misclassified as equity
        ScenarioPnl eq = r.scenarios().stream()
                .filter(s -> s.scenario().equals("EQUITY_-10%")).findFirst().orElseThrow();
        assertThat(eq.pnl()).isEqualTo(0.0); // a bond takes no equity shock
    }

    @Test
    void biasCallout_varAssumesFactorIndependence() {
        // KNOWN SIMPLIFICATION (documented): parametric VaR treats the factors as independent,
        // so diversified < undiversified. But in the RISK_OFF tail the factors move TOGETHER,
        // so the diversified number UNDERSTATES the risk it exists to measure. This pins the
        // direction: on a mixed (rate + equity) book the diversification benefit is strictly
        // positive under the independence assumption.
        PositionService ps = mock(PositionService.class);
        when(ps.forPortfolio("P")).thenReturn(List.of(bondPosition("1000000"), equityPosition("100000")));
        Clock clock = Clock.fixed(Instant.parse("2026-01-15T00:00:00Z"), ZoneOffset.UTC);

        PortfolioRiskReport r = new RiskEngine(ps, clock).compute("P");

        assertThat(r.var95Diversified()).isLessThan(r.var95Undiversified());
        assertThat(r.diversificationBenefit()).isGreaterThan(0.0);
    }
}
