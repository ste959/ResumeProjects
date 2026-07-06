package com.bonddesk.oms.strategy;

/**
 * Almgren–Chriss optimal execution: the risk-averse trader front-loads trading to reduce
 * exposure to price risk, trading off market impact against variance. The optimal holding
 * trajectory is
 *
 * <pre>  x_j = X · sinh(κ(N−j)) / sinh(κN)  </pre>
 *
 * where {@code κ} encodes urgency/risk-aversion. κ→0 recovers a linear (TWAP) schedule;
 * larger κ front-loads. The per-slice child sizes are x_{j-1} − x_j.
 */
public final class AlmgrenChrissExecution extends ExecutionStrategy {

    private final double[] schedule;

    public AlmgrenChrissExecution(boolean buy, double totalSize, int slices, double kappa) {
        super(buy, totalSize, slices);
        this.schedule = buildSchedule(totalSize, this.slices, kappa);
    }

    @Override
    public String type() {
        return "ALMGREN_CHRISS";
    }

    @Override
    protected double plannedChild(StrategyContext ctx) {
        return sliceIndex < schedule.length ? schedule[sliceIndex] : 0.0;
    }

    private static double[] buildSchedule(double total, int n, double kappa) {
        double[] child = new double[n];
        if (kappa <= 1e-9) { // κ→0 → uniform (TWAP)
            for (int i = 0; i < n; i++) child[i] = total / n;
            return child;
        }
        double denom = Math.sinh(kappa * n);
        double prev = total; // holdings before slice 0 = X
        for (int j = 1; j <= n; j++) {
            double x = total * Math.sinh(kappa * (n - j)) / denom; // holdings after slice j
            child[j - 1] = prev - x;
            prev = x;
        }
        return child;
    }
}
