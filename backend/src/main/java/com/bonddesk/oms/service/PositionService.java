package com.bonddesk.oms.service;

import com.bonddesk.oms.domain.OrderSide;
import com.bonddesk.oms.domain.Position;
import com.bonddesk.oms.domain.Security;
import com.bonddesk.oms.repository.PositionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.util.List;

/**
 * Maintains the desk's holdings incrementally as fills arrive. Keeps a signed net
 * quantity (long positive, short negative) and a quantity-weighted average cost,
 * handling the three cases every position book must: adding to a position, reducing
 * it, and flipping through zero to the other side.
 */
@Service
public class PositionService {

    private static final int PRICE_SCALE = 4;

    private final PositionRepository positions;
    private final Clock clock;

    public PositionService(PositionRepository positions, Clock clock) {
        this.positions = positions;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<Position> forPortfolio(String portfolio) {
        return positions.findByPortfolioOrderBySecurity_Cusip(portfolio);
    }

    /**
     * Apply a single fill to the (portfolio, security) holding and return the updated
     * position. Creates the position on first fill.
     */
    @Transactional
    public Position applyFill(String portfolio, Security security, OrderSide side,
                              BigDecimal fillQty, BigDecimal price) {
        Position pos = positions.findByPortfolioAndSecurity_Cusip(portfolio, security.getCusip())
                .orElseGet(() -> new Position(portfolio, security));

        BigDecimal signedQty = side == OrderSide.BUY ? fillQty : fillQty.negate();
        BigDecimal oldNet = pos.getNetQuantity();
        BigDecimal oldAvg = pos.getAvgCost();
        BigDecimal newNet = oldNet.add(signedQty);

        pos.setAvgCost(nextAvgCost(oldNet, oldAvg, signedQty, newNet, price));
        pos.setNetQuantity(newNet);
        pos.setUpdatedAt(clock.instant());
        return positions.save(pos);
    }

    /**
     * Snap the (portfolio, security) holding to an ABSOLUTE net quantity and average cost,
     * creating the position on first sight. This is the reconcile primitive — it overwrites the
     * book with the broker's truth, distinct from {@link #applyFill} which applies a signed delta.
     */
    @Transactional
    public Position setPosition(String portfolio, Security security, BigDecimal netQty, BigDecimal avgCost) {
        Position pos = positions.findByPortfolioAndSecurity_Cusip(portfolio, security.getCusip())
                .orElseGet(() -> new Position(portfolio, security));
        pos.setNetQuantity(netQty == null ? BigDecimal.ZERO : netQty);
        pos.setAvgCost(avgCost == null ? BigDecimal.ZERO : avgCost);
        pos.setUpdatedAt(clock.instant());
        return positions.save(pos);
    }

    /**
     * Weighted-average cost after a fill.
     * <ul>
     *   <li>Opening from flat, or adding in the same direction → blend old and new.</li>
     *   <li>Reducing but staying on the same side → cost unchanged.</li>
     *   <li>Closing to flat → cost resets to zero.</li>
     *   <li>Flipping through zero → cost becomes the new trade price for the residual.</li>
     * </ul>
     */
    private BigDecimal nextAvgCost(BigDecimal oldNet, BigDecimal oldAvg,
                                   BigDecimal signedQty, BigDecimal newNet, BigDecimal price) {
        if (oldNet.signum() == 0) {
            return price;
        }
        if (oldNet.signum() == signedQty.signum()) {
            BigDecimal oldAbs = oldNet.abs();
            BigDecimal addAbs = signedQty.abs();
            return oldAbs.multiply(oldAvg).add(addAbs.multiply(price))
                    .divide(oldAbs.add(addAbs), PRICE_SCALE, RoundingMode.HALF_UP);
        }
        if (newNet.signum() == 0) {
            return BigDecimal.ZERO;
        }
        return oldNet.signum() == newNet.signum() ? oldAvg : price;
    }
}
