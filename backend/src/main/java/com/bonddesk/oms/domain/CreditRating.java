package com.bonddesk.oms.domain;

/**
 * Simplified credit rating scale (S&amp;P style), ordered best-to-worst by ordinal.
 *
 * <p>Because the constants are declared from highest to lowest quality, a lower
 * {@code ordinal()} means a stronger rating. That lets compliance express a rule
 * like "no bonds weaker than BBB-" as a simple ordinal comparison.
 */
public enum CreditRating {
    AAA,
    AA_PLUS, AA, AA_MINUS,
    A_PLUS, A, A_MINUS,
    BBB_PLUS, BBB, BBB_MINUS,   // lowest investment-grade band ends here
    BB_PLUS, BB, BB_MINUS,
    B_PLUS, B, B_MINUS,
    CCC, CC, C, D;

    /** Lowest rating still considered investment grade. */
    public static final CreditRating LOWEST_INVESTMENT_GRADE = BBB_MINUS;

    /** @return true if this rating is at least as strong as {@code floor}. */
    public boolean isAtLeast(CreditRating floor) {
        return this.ordinal() <= floor.ordinal();
    }

    public boolean isInvestmentGrade() {
        return isAtLeast(LOWEST_INVESTMENT_GRADE);
    }
}
