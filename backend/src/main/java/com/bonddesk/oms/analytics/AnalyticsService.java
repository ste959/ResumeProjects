package com.bonddesk.oms.analytics;

import com.bonddesk.oms.domain.OrderSide;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/**
 * Reporting / analytics read model, written in hand-crafted SQL via {@link JdbcTemplate}
 * rather than the ORM. The transactional side of the system uses JPA; reporting uses
 * direct SQL — a common split that keeps complex analytical queries (joins, aggregates,
 * window functions) explicit and tunable instead of fighting an object mapper.
 *
 * <p>All queries are written to run unchanged on both PostgreSQL (prod) and H2 in
 * PostgreSQL-compatibility mode (dev/test).
 */
@Service
public class AnalyticsService {

    private static final BigDecimal BPS = BigDecimal.valueOf(10_000);
    private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

    private final JdbcTemplate jdbc;

    public AnalyticsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Transaction cost analysis: for each security and side, the volume-weighted average
     * fill price versus the security's benchmark, expressed as slippage in basis points.
     * Joins orders → executions → security and aggregates.
     */
    @Transactional(readOnly = true)
    public List<ExecutionQuality> executionQuality() {
        String sql = """
                SELECT s.cusip                              AS cusip,
                       s.description                        AS description,
                       o.side                               AS side,
                       COUNT(DISTINCT o.id)                 AS order_count,
                       SUM(e.quantity)                      AS filled_face,
                       SUM(e.quantity * e.price) / SUM(e.quantity) AS avg_fill_price,
                       s.clean_price                        AS benchmark_price
                FROM execution e
                JOIN orders o   ON o.id = e.order_id
                JOIN security s ON s.cusip = o.cusip
                GROUP BY s.cusip, s.description, o.side, s.clean_price
                ORDER BY filled_face DESC
                """;
        return jdbc.query(sql, executionQualityMapper());
    }

    /** Highest-volume securities by filled par notional. */
    @Transactional(readOnly = true)
    public List<SecurityVolume> topSecuritiesByVolume(int limit) {
        String sql = """
                SELECT s.cusip        AS cusip,
                       s.description  AS description,
                       SUM(e.quantity) AS traded_face,
                       COUNT(e.id)     AS fill_count
                FROM execution e
                JOIN orders o   ON o.id = e.order_id
                JOIN security s ON s.cusip = o.cusip
                GROUP BY s.cusip, s.description
                ORDER BY traded_face DESC
                LIMIT ?
                """;
        return jdbc.query(sql, (rs, i) -> new SecurityVolume(
                rs.getString("cusip"),
                rs.getString("description"),
                rs.getBigDecimal("traded_face"),
                rs.getLong("fill_count")), limit);
    }

    /** Firm-wide order counts and fill rate, via conditional aggregation in one pass. */
    @Transactional(readOnly = true)
    public DeskSummary deskSummary() {
        String sql = """
                SELECT COUNT(*) AS total_orders,
                       SUM(CASE WHEN status = 'FILLED' THEN 1 ELSE 0 END)   AS filled_orders,
                       SUM(CASE WHEN status = 'REJECTED' THEN 1 ELSE 0 END) AS rejected_orders,
                       SUM(CASE WHEN status IN ('NEW','STAGED','ROUTED','PARTIALLY_FILLED')
                                THEN 1 ELSE 0 END)                          AS working_orders,
                       COALESCE(SUM(filled_quantity), 0)                    AS total_filled_face
                FROM orders
                """;
        return jdbc.queryForObject(sql, (rs, i) -> {
            long total = rs.getLong("total_orders");
            long filled = rs.getLong("filled_orders");
            BigDecimal fillRate = total == 0 ? BigDecimal.ZERO
                    : BigDecimal.valueOf(filled).multiply(HUNDRED)
                    .divide(BigDecimal.valueOf(total), 1, RoundingMode.HALF_UP);
            return new DeskSummary(total, filled,
                    rs.getLong("working_orders"), rs.getLong("rejected_orders"),
                    rs.getBigDecimal("total_filled_face"), fillRate);
        });
    }

    /**
     * Daily traded volume with a running cumulative total. Uses a CTE to roll fills up to
     * a day, then a window function ({@code SUM() OVER (ORDER BY ...)}) for the running sum.
     */
    @Transactional(readOnly = true)
    public List<DailyVolume> dailyVolume() {
        String sql = """
                WITH daily AS (
                    SELECT CAST(e.executed_at AS DATE) AS trade_date,
                           SUM(e.quantity)             AS daily_face
                    FROM execution e
                    GROUP BY CAST(e.executed_at AS DATE)
                )
                SELECT trade_date,
                       daily_face,
                       SUM(daily_face) OVER (ORDER BY trade_date) AS cumulative_face
                FROM daily
                ORDER BY trade_date
                """;
        return jdbc.query(sql, (rs, i) -> new DailyVolume(
                rs.getObject("trade_date", java.time.LocalDate.class),
                rs.getBigDecimal("daily_face"),
                rs.getBigDecimal("cumulative_face")));
    }

    private RowMapper<ExecutionQuality> executionQualityMapper() {
        return (rs, i) -> {
            OrderSide side = OrderSide.valueOf(rs.getString("side"));
            BigDecimal avg = rs.getBigDecimal("avg_fill_price");
            BigDecimal benchmark = rs.getBigDecimal("benchmark_price");
            return new ExecutionQuality(
                    rs.getString("cusip"),
                    rs.getString("description"),
                    side,
                    rs.getLong("order_count"),
                    rs.getBigDecimal("filled_face"),
                    avg.setScale(4, RoundingMode.HALF_UP),
                    benchmark,
                    slippageBps(side, avg, benchmark));
        };
    }

    /**
     * Signed slippage in bps. A BUY that fills above the benchmark is a cost (positive);
     * a SELL that fills below the benchmark is likewise a cost (positive).
     */
    private BigDecimal slippageBps(OrderSide side, BigDecimal avgFill, BigDecimal benchmark) {
        if (benchmark == null || benchmark.signum() == 0 || avgFill == null) {
            return BigDecimal.ZERO;
        }
        BigDecimal deviation = avgFill.subtract(benchmark)
                .divide(benchmark, 8, RoundingMode.HALF_UP)
                .multiply(BPS);
        if (side == OrderSide.SELL) {
            deviation = deviation.negate();
        }
        return deviation.setScale(1, RoundingMode.HALF_UP);
    }
}
