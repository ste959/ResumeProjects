package com.bonddesk.oms.strategy;

/**
 * Avellaneda–Stoikov market maker (stationary / infinite-horizon variant).
 *
 * <p>Each tick it centres its quotes on an inventory-skewed <em>reservation price</em>
 * and sets a spread that trades off expected fill rate against inventory risk:
 *
 * <pre>
 *   reservation r = s − q·γ·σ²·τ
 *   half-spread   = ½·(γ·σ²·τ + (2/γ)·ln(1 + γ/κ))
 *   bid = r − half,  ask = r + half
 * </pre>
 *
 * where {@code s} is the microprice, {@code q} inventory, {@code γ} risk aversion,
 * {@code σ} volatility, {@code κ} order-flow intensity and {@code τ} an effective
 * time-horizon. As inventory grows the reservation price shifts to lean against it —
 * quoting more aggressively on the side that reduces the position.
 */
public final class AvellanedaStoikovMaker implements Strategy {

    private final double gamma;   // risk aversion
    private final double kappa;   // order-flow intensity
    private final double tau;     // effective time-to-horizon (ticks)
    private final double quoteSize;

    public AvellanedaStoikovMaker(double gamma, double kappa, double tau, double quoteSize) {
        this.gamma = gamma;
        this.kappa = kappa;
        this.tau = tau;
        this.quoteSize = quoteSize;
    }

    @Override
    public String type() {
        return "AVELLANEDA_STOIKOV";
    }

    @Override
    public void step(StrategyContext ctx) {
        MarketState s = ctx.state();
        double mid = s.microprice() > 0 ? s.microprice() : s.mid();
        double q = ctx.position();
        double sigma = s.sigma();

        double reservation = mid - q * gamma * sigma * sigma * tau;
        double halfSpread = 0.5 * (gamma * sigma * sigma * tau + (2.0 / gamma) * Math.log(1.0 + gamma / kappa));

        double bid = reservation - halfSpread;
        double ask = reservation + halfSpread;
        // Never quote a crossed or non-positive book.
        if (bid <= 0 || ask <= bid) {
            bid = s.bestBid();
            ask = s.bestAsk();
        }
        ctx.setQuotes(bid, ask, quoteSize);
    }
}
