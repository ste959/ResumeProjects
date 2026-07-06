package com.bonddesk.oms.strategy;

import java.util.ArrayList;
import java.util.List;

/**
 * Signed inventory with average-cost accounting and realized/unrealized P&L — the shared
 * ledger for every strategy. Handles adding, reducing, closing and flipping a position,
 * booking realized P&L on the closed portion.
 */
public final class PnlBook {

    private double position;   // signed: +long / -short
    private double avgCost;
    private double realized;
    private final List<Fill> fills = new ArrayList<>();

    public synchronized void apply(Fill fill) {
        fills.add(fill);
        double signed = fill.isBuy() ? fill.size() : -fill.size();
        double price = fill.price();

        if (position == 0) {
            avgCost = price;
        } else if (Math.signum(position) == Math.signum(signed)) {
            // Adding to the position → blend the average cost.
            double newAbs = Math.abs(position) + fill.size();
            avgCost = (Math.abs(position) * avgCost + fill.size() * price) / newAbs;
        } else {
            // Reducing / closing / flipping → realize P&L on the closed quantity.
            double closed = Math.min(fill.size(), Math.abs(position));
            realized += closed * (price - avgCost) * Math.signum(position);
            double newPos = position + signed;
            if (Math.signum(newPos) != Math.signum(position) && newPos != 0) {
                avgCost = price; // flipped through zero: residual is at the trade price
            } else if (newPos == 0) {
                avgCost = 0;
            }
        }
        position += signed;
    }

    public double position() { return position; }
    public double avgCost() { return avgCost; }
    public double realized() { return realized; }
    public List<Fill> fills() { return fills; }

    public double unrealized(double mark) {
        return position * (mark - avgCost);
    }

    public double totalPnl(double mark) {
        return realized + unrealized(mark);
    }
}
