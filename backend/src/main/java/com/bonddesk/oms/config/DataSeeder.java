package com.bonddesk.oms.config;

import com.bonddesk.oms.domain.AssetClass;
import com.bonddesk.oms.domain.CreditRating;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.repository.SecurityRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

/**
 * Seeds the bond security master on startup if it is empty. Kept in code (rather than a
 * SQL seed) so the same reference data loads under both the H2 and PostgreSQL profiles.
 * Includes a restricted name and a sub-investment-grade name so the compliance rules
 * are demonstrable out of the box.
 */
@Component
public class DataSeeder implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(DataSeeder.class);

    private final SecurityRepository securities;

    public DataSeeder(SecurityRepository securities) {
        this.securities = securities;
    }

    @Override
    public void run(String... args) {
        if (securities.count() > 0) {
            return;
        }
        List<Security> seed = List.of(
                bond("912828YK0", "US912828YK08", "US TREASURY N/B 1.5% 2030", "US TREASURY",
                        "1.5000", "2030-08-15", "SOVEREIGN", CreditRating.AAA, "97.8200", false),
                bond("91282CFX4", "US91282CFX41", "US TREASURY N/B 4.0% 2034", "US TREASURY",
                        "4.0000", "2034-02-15", "SOVEREIGN", CreditRating.AAA, "99.4500", false),
                bond("912810TW8", "US912810TW80", "US TREASURY BOND 4.25% 2054", "US TREASURY",
                        "4.2500", "2054-05-15", "SOVEREIGN", CreditRating.AAA, "98.1000", false),
                bond("037833EB2", "US037833EB29", "APPLE INC 3.85% 2043", "APPLE INC",
                        "3.8500", "2043-05-04", "CORPORATE", CreditRating.AA_PLUS, "89.7500", false),
                bond("594918BR4", "US594918BR43", "MICROSOFT CORP 2.525% 2050", "MICROSOFT CORP",
                        "2.5250", "2050-06-01", "CORPORATE", CreditRating.AAA, "68.4000", false),
                bond("46625HRL6", "US46625HRL65", "JPMORGAN CHASE 4.452% 2038", "JPMORGAN CHASE & CO",
                        "4.4520", "2038-12-05", "CORPORATE", CreditRating.A_MINUS, "94.2000", false),
                bond("06051GHF9", "US06051GHF95", "BANK OF AMERICA 3.593% 2028", "BANK OF AMERICA CORP",
                        "3.5930", "2028-07-21", "CORPORATE", CreditRating.A_MINUS, "96.8800", false),
                bond("816851BH1", "US816851BH19", "SEMPRA ENERGY 3.8% 2038", "SEMPRA",
                        "3.8000", "2038-02-01", "UTILITY", CreditRating.BBB, "88.5000", false),
                bond("278642AX0", "US278642AX07", "EBAY INC 3.6% 2027", "EBAY INC",
                        "3.6000", "2027-06-05", "CORPORATE", CreditRating.BBB_PLUS, "97.1500", false),
                bond("035240AN9", "US035240AN91", "ANHEUSER-BUSCH 4.9% 2046", "ANHEUSER-BUSCH INBEV",
                        "4.9000", "2046-02-01", "CORPORATE", CreditRating.BBB, "92.3000", false),
                // Sub-investment-grade: BUY orders are blocked by MinCreditRatingRule.
                bond("122017PZ2", "US122017PZ26", "BURLINGTON HLDG 6.25% 2036", "BURLINGTON HOLDINGS",
                        "6.2500", "2036-04-15", "CORPORATE", CreditRating.B_PLUS, "84.5000", false),
                // Restricted: all trading blocked by RestrictedSecurityRule.
                bond("999999XX9", "US999999XX90", "PROJECT MERIDIAN 5.0% 2032 (RESTRICTED)", "MERIDIAN SPV",
                        "5.0000", "2032-09-30", "CORPORATE", CreditRating.BBB_MINUS, "100.0000", true),

                // Listed equities — routed to the lit order book (Alpaca) rather than RFQ.
                // The clean_price here is only an indicative fallback; the live feed overrides it.
                // Tickers match the equity market-data / execution symbols.
                equity("037833100", "AAPL", "US0378331005", "APPLE INC", "TECHNOLOGY", "232.50"),
                equity("594918104", "MSFT", "US5949181045", "MICROSOFT CORP", "TECHNOLOGY", "430.00"),
                equity("67066G104", "NVDA", "US67066G1040", "NVIDIA CORP", "SEMICONDUCTORS", "128.00"),
                equity("023135106", "AMZN", "US0231351067", "AMAZON.COM INC", "CONSUMER DISCRETIONARY", "205.00"),
                equity("46625H100", "JPM", "US46625H1005", "JPMORGAN CHASE & CO", "FINANCIALS", "265.00"),
                equity("88160R101", "TSLA", "US88160R1014", "TESLA INC", "CONSUMER DISCRETIONARY", "340.00")
        );
        securities.saveAll(seed);
        long bonds = seed.stream().filter(s -> s.getAssetClass() == AssetClass.FIXED_INCOME).count();
        long equities = seed.size() - bonds;
        log.info("Seeded {} securities into the security master ({} bonds, {} equities)",
                seed.size(), bonds, equities);
    }

    private static Security bond(String cusip, String isin, String description, String issuer,
                                 String coupon, String maturity, String sector,
                                 CreditRating rating, String cleanPrice, boolean restricted) {
        Security s = new Security();
        s.setAssetClass(AssetClass.FIXED_INCOME);
        s.setCusip(cusip);
        s.setIsin(isin);
        s.setDescription(description);
        s.setIssuer(issuer);
        s.setCouponRate(new BigDecimal(coupon));
        s.setMaturityDate(LocalDate.parse(maturity));
        s.setFaceValue(new BigDecimal("1000.00"));
        s.setCurrency("USD");
        s.setSector(sector);
        s.setRating(rating);
        s.setCleanPrice(new BigDecimal(cleanPrice));
        s.setRestricted(restricted);
        return s;
    }

    /**
     * A listed equity: no coupon/maturity/rating (those are fixed-income concepts), a
     * ticker for the market-data feed, and a price quoted in dollars per share.
     */
    private static Security equity(String cusip, String ticker, String isin, String issuer,
                                   String sector, String price) {
        Security s = new Security();
        s.setAssetClass(AssetClass.EQUITY);
        s.setCusip(cusip);
        s.setTicker(ticker);
        s.setIsin(isin);
        s.setDescription(issuer + " COMMON STOCK");
        s.setIssuer(issuer);
        s.setCurrency("USD");
        s.setSector(sector);
        s.setCleanPrice(new BigDecimal(price));
        s.setRestricted(false);
        return s;
    }
}
