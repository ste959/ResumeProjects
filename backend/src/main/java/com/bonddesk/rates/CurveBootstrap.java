package com.bonddesk.rates;

/**
 * Bootstraps a discount curve from a par curve. Treats each par yield as a par-swap (equivalently a
 * par-bond) rate on the pillar grid and solves the pillar discount factors sequentially, so every
 * input instrument reprices to par by construction — the standard curve-construction step a rates
 * desk runs before it can price or risk anything.
 *
 * <p>For a par rate {@code S_n} with payment schedule {@code t_1..t_n} (accruals τ_i = t_i − t_{i-1}):
 * <pre>
 *     1 = S_n · Σ_{i≤n} τ_i · DF(t_i)  +  DF(t_n)
 *     ⇒ DF(t_n) = (1 − S_n · Σ_{i&lt;n} τ_i·DF(t_i)) / (1 + S_n·τ_n)
 * </pre>
 */
public final class CurveBootstrap {

    private CurveBootstrap() {}

    /** @param tenors pillar years (ascending); @param parPct par yields in percent (4.25 = 4.25%). */
    public static RateCurve fromPar(double[] tenors, double[] parPct) {
        int n = tenors.length;
        double[] df = new double[n];
        double annuity = 0.0;                      // Σ τ_i · DF(t_i) accumulated over solved pillars
        for (int i = 0; i < n; i++) {
            double s = parPct[i] / 100.0;
            double tau = tenors[i] - (i == 0 ? 0.0 : tenors[i - 1]);
            df[i] = (1.0 - s * annuity) / (1.0 + s * tau);
            annuity += tau * df[i];
        }
        double[] zeros = new double[n];
        for (int i = 0; i < n; i++) {
            zeros[i] = -Math.log(df[i]) / tenors[i];
        }
        return new RateCurve(tenors, zeros);
    }
}
