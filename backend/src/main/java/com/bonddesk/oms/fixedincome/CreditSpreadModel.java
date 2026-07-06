package com.bonddesk.oms.fixedincome;

import com.bonddesk.oms.domain.CreditRating;
import com.bonddesk.oms.domain.Security;
import org.springframework.stereotype.Component;

/**
 * Indicative credit spread (basis points over the Treasury curve) by rating. Sovereigns
 * price on the curve itself (zero spread); corporates add a spread that widens as credit
 * quality falls. These are representative levels — a production desk would source live
 * option-adjusted spreads (e.g. ICE BofA indices via FRED) per rating bucket.
 */
@Component
public class CreditSpreadModel {

    /** Credit spread in basis points to add to the benchmark curve yield. */
    public double spreadBps(Security security) {
        if (isSovereign(security)) {
            return 0.0;
        }
        CreditRating rating = security.getRating();
        if (rating == null) {
            return 150.0;
        }
        return switch (rating) {
            case AAA -> 25;
            case AA_PLUS -> 35;
            case AA -> 45;
            case AA_MINUS -> 55;
            case A_PLUS -> 65;
            case A -> 75;
            case A_MINUS -> 90;
            case BBB_PLUS -> 110;
            case BBB -> 135;
            case BBB_MINUS -> 170;
            case BB_PLUS -> 230;
            case BB -> 290;
            case BB_MINUS -> 350;
            case B_PLUS -> 430;
            case B -> 520;
            case B_MINUS -> 620;
            case CCC -> 800;
            case CC -> 1000;
            case C -> 1200;
            case D -> 1500;
        };
    }

    private boolean isSovereign(Security security) {
        String sector = security.getSector();
        return sector != null && (sector.equalsIgnoreCase("SOVEREIGN") || sector.equalsIgnoreCase("TREASURY"));
    }
}
